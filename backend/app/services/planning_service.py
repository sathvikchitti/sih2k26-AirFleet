"""Read-only multi-work-order planning over a frozen in-memory snapshot.

This service produces recommendations only. It never creates audit events,
transfers, reservations, inventory movements, or work-order transitions.
Live approval remains responsible for validating the current repositories.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math
import random
from typing import Any

from ..domain.enums import PRIORITY_ORDER, TransferStatus, WorkOrderStatus
from ..repositories import OPEN_WORK_ORDER_STATUSES, PartRepository, snapshot
from .ml import get_provider, predict_validated
from .recommendation_service import evaluate_candidates_from_snapshot
from .resource_service import ResourceContext, search_from_snapshot


def _open_orders(state: dict[str, Any], selected_ids: list[str] | None,
                 order_policy: str = "priority") -> tuple[list[dict], list[dict], list[str]]:
    all_open = [row for row in state.get("work_orders", [])
                if row.get("status") in OPEN_WORK_ORDER_STATUSES]
    if selected_ids is None:
        requested = None
        unknown: list[str] = []
    else:
        requested = list(dict.fromkeys(str(value).upper() for value in selected_ids))
        open_ids = {str(row.get("id", "")).upper() for row in all_open}
        unknown = [value for value in requested if value not in open_ids]

    if order_policy not in {"priority", "first_come_first_served"}:
        raise ValueError(f"unsupported allocation order policy: {order_policy}")

    def order(row: dict) -> tuple:
        if order_policy == "first_come_first_served":
            return (str(row.get("created_at") or ""), str(row.get("id") or ""))
        priority = PRIORITY_ORDER.get(row.get("priority"), 0)
        return (-int(priority), str(row.get("created_at") or ""), str(row.get("id") or ""))

    ordered_all = sorted(all_open, key=order)
    if requested is None:
        selected = list(ordered_all)
    else:
        requested_set = set(requested)
        selected = [row for row in ordered_all if str(row.get("id", "")).upper() in requested_set]
    return ordered_all, selected, unknown


def _available(inv: dict | None) -> int:
    if not inv:
        return 0
    return max(0, int(inv.get("quantity", 0)) - int(inv.get("reserved", 0))
               - int(inv.get("minimum_reserve", 0)))


def _part_min_condition(component: str, resource_context: ResourceContext | None) -> int:
    value = (resource_context.part_min_condition(component) if resource_context
             else PartRepository.min_condition_pct(component))
    if value is None:
        raise ValueError(f"unknown part in planning context: {component}")
    return int(value)


def _part_is_known(component: str, resource_context: ResourceContext | None) -> bool:
    return (resource_context.part(component) is not None if resource_context
            else PartRepository.get(component) is not None)


def _local_usable(inv: dict | None, component: str | None,
                  resource_context: ResourceContext | None = None) -> bool:
    return bool(inv and component and _available(inv) > 0
                and int(inv.get("condition_pct", 0)) >= _part_min_condition(component, resource_context))


def _procurement_condition_compatible(inv: dict | None, component: str,
                                      resource_context: ResourceContext | None) -> bool:
    """Do not claim replenishment repairs a positive, below-minimum pooled line."""
    if not inv or int(inv.get("quantity", 0)) <= 0:
        return True
    return int(inv.get("condition_pct", 0)) >= _part_min_condition(component, resource_context)


def _arrival_serviceability(transfer: dict, destination_inventory: dict | None,
                            component: str,
                            resource_context: ResourceContext | None = None) -> dict[str, Any]:
    """Project whether an in-transit unit will satisfy current start rules.

    Inventory condition is pooled by base/component. Match receipt semantics:
    an empty line takes the incoming grade; a stocked line keeps the lower of
    its current grade and the incoming grade. This is conservative because the
    repository does not track individual lot condition.
    """
    current = destination_inventory or {}
    transfer_component = str(transfer.get("part_number") or "").upper()
    transfer_destination = str(transfer.get("dest_base") or transfer.get("destination_base") or "").lower()
    transfer_aircraft = transfer.get("for_aircraft") or transfer.get("aircraft_id")
    work_order_base = str(transfer.get("_work_order_base") or "").lower()
    work_order_aircraft = transfer.get("_work_order_aircraft")
    if (transfer_component != str(component).upper()
            or (transfer_destination and work_order_base and transfer_destination != work_order_base)
            or (transfer_aircraft and work_order_aircraft
                and str(transfer_aircraft).upper() != str(work_order_aircraft).upper())):
        return {
            "can_start_on_arrival": False,
            "arrival_block_reason": "TRANSFER_WORK_ORDER_MISMATCH",
            "destination_condition_after_receipt_pct": None,
            "available_for_transfer_after_receipt": 0,
        }
    quantity_before = int(current.get("quantity", 0))
    incoming_quantity = int(transfer.get("quantity", 1))
    reserved = int(current.get("reserved", 0))
    minimum_reserve = int(current.get("minimum_reserve", 0))
    incoming_condition = transfer.get("condition_pct")
    current_condition = current.get("condition_pct")

    if incoming_condition is None:
        projected_condition = None
    elif quantity_before > 0:
        projected_condition = min(int(current_condition or 0), int(incoming_condition))
    else:
        projected_condition = int(incoming_condition)

    available_after_receipt = max(
        0, quantity_before + incoming_quantity - reserved - minimum_reserve,
    )
    minimum_condition = _part_min_condition(component, resource_context)
    if projected_condition is None or projected_condition < minimum_condition:
        reason = "DESTINATION_CONDITION_BELOW_MINIMUM"
    elif available_after_receipt <= 0:
        reason = "NO_TRANSFERABLE_DESTINATION_STOCK"
    else:
        reason = None
    return {
        "can_start_on_arrival": reason is None,
        "arrival_block_reason": reason,
        "destination_condition_after_receipt_pct": projected_condition,
        "available_for_transfer_after_receipt": available_after_receipt,
    }


def _allocation_row(work_order: dict, allocation_status: str, **extra) -> dict:
    return {
        "work_order_id": work_order.get("id"),
        "aircraft_id": work_order.get("aircraft_id"),
        "destination_base": work_order.get("base_id"),
        "required_component": work_order.get("required_component"),
        "work_order_status": work_order.get("status"),
        "priority": work_order.get("priority"),
        "created_at": work_order.get("created_at"),
        "allocation_status": allocation_status,
        **extra,
    }


def allocation_preview(work_order_ids: list[str] | None = None, *,
                       source_policy: str = "proposed",
                       allocate_new: bool = True,
                       _state: dict[str, Any] | None = None,
                       _predictions: dict[str, dict] | None = None,
                       resource_context: ResourceContext | None = None,
                       order_policy: str = "priority",
                       procurement_lead_hours: float | None = None,
                       _rng: random.Random | None = None) -> dict[str, Any]:
    """Allocate shared donor/local stock on a clone, using priority/age/id.

    Feasible candidates and their costs come from the same search and ranking
    helpers used by single-work-order recommendations. Local stock and linked
    transfer lifecycle state are accounted for before proposing new transfers.
    """
    if source_policy not in {"proposed", "nearest_feasible", "random_feasible", "local_only_procurement"}:
        raise ValueError(f"unsupported allocation source policy: {source_policy}")
    if procurement_lead_hours is not None and (
        isinstance(procurement_lead_hours, bool)
        or not isinstance(procurement_lead_hours, (int, float))
        or not math.isfinite(float(procurement_lead_hours))
        or procurement_lead_hours < 0
    ):
        raise ValueError("procurement_lead_hours must be a finite nonnegative number")
    state = _state if _state is not None else snapshot()
    all_open_orders, selected_work_orders, unknown_ids = _open_orders(state, work_order_ids, order_policy)
    ids_by_aircraft = sorted({str(row["aircraft_id"]).upper() for row in selected_work_orders
                              if row.get("aircraft_id")})
    if _predictions is None:
        provider = get_provider()
        predictions = {aircraft_id: predict_validated(provider, aircraft_id)
                       for aircraft_id in ids_by_aircraft}
    else:
        predictions = _predictions

    # Clone the one inventory snapshot. All virtual reservations/debits below
    # apply only to this private ledger.
    ledger = deepcopy(state.get("inventory", []))
    inventory_by_key = {(str(row.get("base_id", "")).lower(),
                         str(row.get("part_number", "")).upper()): row
                        for row in ledger}
    work_order_by_id = {str(row.get("id", "")).upper(): row for row in all_open_orders}
    linked_transfers: dict[str, list[dict]] = defaultdict(list)
    ordered_transfers = sorted(state.get("transfers", []),
                               key=lambda row: (str(row.get("created") or row.get("created_at") or ""),
                                                str(row.get("id") or "")))
    for transfer in ordered_transfers:
        wo_id = str(transfer.get("work_order_id") or "").upper()
        if wo_id in work_order_by_id:
            linked_transfers[wo_id].append(transfer)

    rows_by_id: dict[str, dict] = {}
    preallocated: set[str] = set()
    conflicts: list[dict] = []

    # Pending transfers have not changed physical quantity yet, but they are
    # provisional claims on the donor in a what-if allocation. Include both
    # WO-linked and standalone pending transfer requests.
    for transfer in ordered_transfers:
        if transfer.get("status") != TransferStatus.PENDING_APPROVAL.value:
            continue
        component = str(transfer.get("part_number") or "").upper()
        source_inv = inventory_by_key.get((str(transfer.get("source_base", "")).lower(), component))
        quantity = int(transfer.get("quantity", 1))
        if source_inv is None or _available(source_inv) < quantity:
            conflicts.append({
                "work_order_id": transfer.get("work_order_id"),
                "transfer_id": transfer.get("id"),
                "reason": "PENDING_TRANSFER_EXCEEDS_AVAILABLE_STOCK",
            })
        if source_inv is not None:
            source_inv["quantity"] = int(source_inv.get("quantity", 0)) - quantity

    # Existing transfers have authoritative lifecycle semantics. Pending stock
    # is provisionally removed from the planning ledger; in-transit stock was
    # already debited physically; received stock is earmarked locally unless a
    # real maintenance reservation already accounts for it.
    for work_order in all_open_orders:
        wo_id = str(work_order.get("id", "")).upper()
        component = str(work_order.get("required_component") or "").upper()
        transfers = linked_transfers.get(wo_id, [])
        active = [t for t in transfers if t.get("status") in {
            TransferStatus.PENDING_APPROVAL.value, TransferStatus.IN_TRANSIT.value,
        }]
        in_transit = [t for t in active if t.get("status") == TransferStatus.IN_TRANSIT.value]
        received = [t for t in transfers if t.get("status") == TransferStatus.RECEIVED.value]
        inv = inventory_by_key.get((str(work_order.get("base_id", "")).lower(), component))

        if active:
            # Prefer the furthest authoritative lifecycle state for display.
            # Every pending transfer was already provisionally debited above;
            # IN_TRANSIT stock was debited by the real service.
            transfer = in_transit[0] if in_transit else active[0]
            if len(active) > 1:
                conflicts.append({
                    "work_order_id": work_order["id"],
                    "transfer_ids": [row.get("id") for row in active],
                    "reason": "MULTIPLE_ACTIVE_TRANSFERS_FOR_WORK_ORDER",
                })
            if transfer.get("status") == TransferStatus.PENDING_APPROVAL.value:
                status = "EXISTING_PENDING_APPROVAL"
                arrival_projection = {}
            else:
                # Dispatch already debited the source; do not debit it twice or
                # expose the in-transit unit as destination stock. A projected
                # arrival only enables maintenance if the actual receipt would
                # satisfy the same pooled condition and reserve checks as start.
                status = "EXISTING_IN_TRANSIT"
                arrival_projection = _arrival_serviceability(
                    {**transfer,
                     "_work_order_base": work_order.get("base_id"),
                     "_work_order_aircraft": work_order.get("aircraft_id")},
                    inv, component, resource_context,
                )
            rows_by_id[wo_id] = _allocation_row(
                work_order, status, transfer_id=transfer.get("id"),
                source_base=transfer.get("source_base"), existing_transfer=True,
                **arrival_projection,
            )
            preallocated.add(wo_id)
            continue

        if received and work_order.get("status") not in {
            WorkOrderStatus.COMPLETED.value, WorkOrderStatus.IN_PROGRESS.value,
        }:
            if work_order.get("resource_reserved"):
                status = "RECEIVED_RESOURCE_RESERVED"
            elif _local_usable(inv, component, resource_context):
                inv["quantity"] = int(inv.get("quantity", 0)) - 1
                status = "RECEIVED_RESOURCE_EARMARKED"
            else:
                status = "RECEIVED_RESOURCE_NOT_AVAILABLE"
                conflicts.append({
                    "work_order_id": work_order["id"],
                    "transfer_ids": [t.get("id") for t in received],
                    "reason": ("RECEIVED_RESOURCE_BELOW_MINIMUM_CONDITION"
                               if inv and int(inv.get("condition_pct", 0))
                               < _part_min_condition(component, resource_context)
                               else "RECEIVED_RESOURCE_NOT_FREE_AT_DESTINATION"),
                })
            rows_by_id[wo_id] = _allocation_row(
                work_order, status,
                transfer_ids=[t.get("id") for t in received], existing_transfer=True,
            )
            preallocated.add(wo_id)
            continue

        if work_order.get("status") == WorkOrderStatus.IN_PROGRESS.value:
            # A normal component WO has a physical reserve, already excluded
            # by `reserved`; legacy in-progress rows without one still need a
            # virtual claim to avoid offering that same local unit elsewhere.
            if work_order.get("resource_reserved"):
                status = "IN_PROGRESS_RESOURCE_RESERVED"
            elif component and _local_usable(inv, component, resource_context):
                inv["quantity"] = int(inv.get("quantity", 0)) - 1
                status = "IN_PROGRESS_LOCAL_EARMARKED"
            else:
                status = "IN_PROGRESS_RESOURCE_UNAVAILABLE"
                conflicts.append({
                    "work_order_id": work_order["id"],
                    "reason": "IN_PROGRESS_WORK_ORDER_HAS_NO_SERVICEABLE_RESOURCE",
                })
            rows_by_id[wo_id] = _allocation_row(work_order, status, existing_allocation=True)
            preallocated.add(wo_id)
            continue

        if work_order.get("status") in {
            WorkOrderStatus.RESOURCE_AVAILABLE.value, WorkOrderStatus.SCHEDULED.value,
        }:
            if _local_usable(inv, component, resource_context):
                inv["quantity"] = int(inv.get("quantity", 0)) - 1
                status = "EXISTING_LOCAL_RESOURCE_EARMARKED"
            else:
                status = "RESOURCE_STATUS_WITHOUT_FREE_LOCAL_UNIT"
                conflicts.append({
                    "work_order_id": work_order["id"],
                    "reason": "WORK_ORDER_RESOURCE_STATE_HAS_NO_FREE_LOCAL_UNIT",
                })
            rows_by_id[wo_id] = _allocation_row(work_order, status, existing_allocation=True)
            preallocated.add(wo_id)

    allocation_order: list[str] = []
    for work_order in selected_work_orders:
        wo_id = str(work_order.get("id", "")).upper()
        if wo_id in preallocated:
            continue
        allocation_order.append(work_order["id"])
        component = work_order.get("required_component")
        if not allocate_new:
            rows_by_id[wo_id] = _allocation_row(
                work_order, "NO_NEW_ALLOCATION", recommended=None,
            )
            continue
        if not component:
            rows_by_id[wo_id] = _allocation_row(work_order, "NO_COMPONENT_SELECTED")
            continue
        if not _part_is_known(str(component), resource_context):
            rows_by_id[wo_id] = _allocation_row(
                work_order, "NO_FEASIBLE_SOURCE", candidates=[], rejected=[], recommended=None,
            )
            continue

        local_inv = inventory_by_key.get((str(work_order.get("base_id", "")).lower(),
                                          str(component).upper()))
        minimum_condition = _part_min_condition(str(component), resource_context)
        local_available = _available(local_inv)
        local_condition = int(local_inv.get("condition_pct", 0)) if local_inv else 0
        if _local_usable(local_inv, str(component), resource_context):
            local_inv["quantity"] = int(local_inv.get("quantity", 0)) - 1
            rows_by_id[wo_id] = _allocation_row(
                work_order, "PROPOSED_LOCAL_ALLOCATION", source_base=work_order["base_id"],
                local_quantity_available_before=local_available,
                local_condition_pct=local_condition,
            )
            continue

        # The evaluation's named local-procurement policy never searches a
        # remote donor. Other policies may use the same explicit fallback only
        # after the shared canonical search returns no feasible donor.
        if source_policy == "local_only_procurement":
            if (procurement_lead_hours is not None
                    and _procurement_condition_compatible(local_inv, str(component), resource_context)):
                minimum_to_order = max(
                    1, int(local_inv.get("reserved", 0) if local_inv else 0)
                    + int(local_inv.get("minimum_reserve", 0) if local_inv else 0)
                    + 1 - int(local_inv.get("quantity", 0) if local_inv else 0),
                )
                rows_by_id[wo_id] = _allocation_row(
                    work_order, "PROPOSED_LOCAL_PROCUREMENT",
                    source_base=work_order["base_id"],
                    procurement_eta_hours=float(procurement_lead_hours),
                    procurement_quantity=minimum_to_order,
                    procurement_condition_pct=minimum_condition,
                    procurement_assumption=True,
                )
            else:
                rows_by_id[wo_id] = _allocation_row(
                    work_order, "NO_FEASIBLE_SOURCE", local_quantity_available_before=local_available,
                    candidates=[], rejected=[], recommended=None,
                )
            continue

        found = search_from_snapshot(work_order, ledger, resource_context=resource_context)
        evaluation = evaluate_candidates_from_snapshot(
            work_order, predictions[str(work_order["aircraft_id"]).upper()], found,
        )
        recommended = evaluation.get("recommended")
        if source_policy == "nearest_feasible" and evaluation.get("candidates"):
            recommended = min(
                evaluation["candidates"],
                key=lambda row: (float(row.get("distance_km") or 0),
                                 float(row.get("eta_hours") or 0),
                                 str(row.get("source_base") or row.get("base_id") or "")),
            )
        elif source_policy == "random_feasible" and evaluation.get("candidates"):
            if _rng is None:
                raise ValueError("random_feasible requires a seeded _rng")
            recommended = _rng.choice(evaluation["candidates"])
        if recommended is None:
            if (procurement_lead_hours is not None
                    and _part_is_known(str(component), resource_context)
                    and _procurement_condition_compatible(local_inv, str(component), resource_context)):
                minimum_to_order = max(
                    1, int(local_inv.get("reserved", 0) if local_inv else 0)
                    + int(local_inv.get("minimum_reserve", 0) if local_inv else 0)
                    + 1 - int(local_inv.get("quantity", 0) if local_inv else 0),
                )
                rows_by_id[wo_id] = _allocation_row(
                    work_order, "PROPOSED_LOCAL_PROCUREMENT",
                    source_base=work_order["base_id"],
                    procurement_eta_hours=float(procurement_lead_hours),
                    procurement_quantity=minimum_to_order,
                    procurement_condition_pct=minimum_condition,
                    procurement_assumption=True,
                    local_quantity_available_before=local_available,
                    candidates=evaluation["candidates"], rejected=evaluation["rejected"],
                )
                continue
            rows_by_id[wo_id] = _allocation_row(
                work_order, "NO_FEASIBLE_SOURCE", local_quantity_available_before=local_available,
                candidates=evaluation["candidates"], rejected=evaluation["rejected"],
                recommended=None,
            )
            continue

        source = str(recommended["source_base"]).lower()
        source_inv = inventory_by_key.get((source, str(component).upper()))
        # The canonical search guarantees a transferable unit at this point.
        # Debit just the preview ledger to represent a shared allocation.
        source_inv["quantity"] = int(source_inv.get("quantity", 0)) - 1
        rows_by_id[wo_id] = _allocation_row(
            work_order, "PROPOSED_REMOTE_TRANSFER", source_base=recommended["source_base"],
            destination_base=work_order["base_id"],
            expected_downtime_hours=recommended["expected_downtime_hours"],
            recommended=recommended, candidates=evaluation["candidates"],
            rejected=evaluation["rejected"],
        )

    before = {(str(row.get("base_id", "")).lower(), str(row.get("part_number", "")).upper()): row
              for row in state.get("inventory", [])}
    inventory_effects = []
    for key in sorted(before):
        initial = before[key]
        after = inventory_by_key[key]
        initial_qty = int(initial.get("quantity", 0))
        virtual_qty = int(after.get("quantity", 0))
        inventory_effects.append({
            "base_id": initial.get("base_id"),
            "part_number": initial.get("part_number"),
            "quantity_at_snapshot": initial_qty,
            "reserved_at_snapshot": int(initial.get("reserved", 0)),
            "minimum_reserve": int(initial.get("minimum_reserve", 0)),
            "available_for_transfer_at_snapshot": _available(initial),
            "condition_pct": int(initial.get("condition_pct", 0)),
            "planned_units_claimed": initial_qty - virtual_qty,
            "virtual_quantity_after_plan": max(0, virtual_qty),
            "virtual_available_for_transfer_after_plan": _available(after),
            "overallocated_units": max(0, -virtual_qty),
        })

    # Return in the deterministic allocation order, including pre-existing
    # commitments in their work-order slots for simple client rendering.
    return {
        "snapshot_type": "read_only_inventory_snapshot",
        "source_policy": source_policy if allocate_new else "no_action",
        "policy": (f"{order_policy}; new source ranked by distance, ETA, base ID"
                   if source_policy == "nearest_feasible" and allocate_new else
                   f"{order_policy}; {source_policy} source selection"),
        "selected_work_order_ids": [row["id"] for row in selected_work_orders],
        "commitment_work_order_ids": [row["id"] for row in all_open_orders
                                      if str(row.get("id", "")).upper() in preallocated],
        "allocation_order": allocation_order,
        "unknown_work_order_ids": unknown_ids,
        "allocations": [rows_by_id[str(row["id"]).upper()] for row in selected_work_orders],
        "inventory_effects": inventory_effects,
        "conflicts": conflicts,
        "mutated_state": False,
        "assumptions": [
            "The snapshot's reserved and minimum-reserve quantities are hard constraints.",
            "Pending transfers provisionally claim donor stock; IN_TRANSIT stock is already debited and is not counted at the destination until receipt.",
            "Received/unreserved and locally serviceable stock is earmarked for its linked/current work order before new proposals.",
            "Proposed allocations are sequential by priority (critical, high, medium, low), then oldest created_at, then work-order ID.",
            "A proposal does not reserve or move stock; live approval must revalidate current inventory and constraints.",
        ],
    }
