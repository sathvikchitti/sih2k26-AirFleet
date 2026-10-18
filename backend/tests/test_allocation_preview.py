"""Focused invariants for the read-only shared-stock allocation preview."""

from __future__ import annotations

from copy import deepcopy

import pytest

from app import data
from app.domain.enums import TransferStatus, WorkOrderStatus
from app.repositories import store
from app.services import planning_service


def _state(monkeypatch):
    state = data.build_seed()
    state["work_orders"] = []
    state["transfers"] = []
    # Keep only inventory/parts needed for targeted scenarios; clear unrelated
    # stock so a test can prove exactly which donor was made available.
    state["inventory"] = [
        {**row, "quantity": 0, "reserved": 0, "minimum_reserve": 0,
         "condition_pct": 0, "status": "STOCKOUT"}
        for row in state["inventory"]
    ]
    monkeypatch.setattr(planning_service, "snapshot", lambda: deepcopy(state))
    monkeypatch.setattr(planning_service, "get_provider", lambda: object())
    monkeypatch.setattr(
        planning_service,
        "predict_validated",
        lambda _provider, aircraft_id: {
            "aircraft_id": aircraft_id, "risk_level": "HIGH", "rul": 30,
            "rul_unit": "cycles", "failure_probability": None,
        },
    )
    return state


def _inventory(state, base, part, qty, *, reserve=0, reserved=0, condition=90):
    row = next((row for row in state["inventory"]
                if row["base_id"] == base and row["part_number"] == part), None)
    if row is None:
        row = {"id": f"test-{base}-{part}", "base_id": base, "part_number": part,
               "quantity": 0, "reserved": 0, "minimum_reserve": 0,
               "condition_pct": 0, "status": "STOCKOUT"}
        state["inventory"].append(row)
    row.update(quantity=qty, minimum_reserve=reserve, reserved=reserved,
               condition_pct=condition, status="AVAILABLE" if qty else "STOCKOUT")
    return row


def _wo(work_order_id, aircraft_id, base_id, *, component="FP-102", priority="HIGH",
        status=WorkOrderStatus.WAITING_FOR_RESOURCE.value, created="2026-01-01T00:00:00Z",
        resource_reserved=False):
    return {
        "id": work_order_id, "aircraft_id": aircraft_id, "base_id": base_id,
        "required_component": component, "priority": priority, "status": status,
        "created_at": created, "estimated_repair_hours": 4,
        "resource_reserved": resource_reserved,
    }


def _allocation(result, work_order_id):
    return next(row for row in result["allocations"]
                if row["work_order_id"] == work_order_id)


def test_preview_is_deterministic_and_does_not_change_state_or_audit(monkeypatch):
    state = _state(monkeypatch)
    state["work_orders"] = [_wo("WO-X", "A17", "alpha")]
    _inventory(state, "bravo", "FP-102", 1)
    before = deepcopy(state)
    audit_before = deepcopy(store()["audit"])

    first = planning_service.allocation_preview()
    second = planning_service.allocation_preview()

    assert first == second
    assert state == before
    assert first["mutated_state"] is False
    assert first["inventory_effects"]
    assert store()["audit"] == audit_before


def test_priority_gets_single_shared_donor_and_ties_are_deterministic(monkeypatch):
    state = _state(monkeypatch)
    _inventory(state, "bravo", "FP-102", 1)
    state["work_orders"] = [
        _wo("WO-Z", "A17", "alpha", priority="HIGH"),
        _wo("WO-A", "A28", "charlie", priority="HIGH"),
    ]

    result = planning_service.allocation_preview(["WO-Z", "WO-A"])
    repeated = planning_service.allocation_preview(["WO-A", "WO-Z"])

    assert result == repeated
    assert result["allocation_order"] == ["WO-A", "WO-Z"]
    assert _allocation(result, "WO-A")["allocation_status"] == "PROPOSED_REMOTE_TRANSFER"
    assert _allocation(result, "WO-Z")["allocation_status"] == "NO_FEASIBLE_SOURCE"
    bravo_effect = next(row for row in result["inventory_effects"]
                        if row["base_id"] == "bravo" and row["part_number"] == "FP-102")
    assert bravo_effect["planned_units_claimed"] == 1
    assert bravo_effect["overallocated_units"] == 0


@pytest.mark.parametrize(
    ("commitment", "status", "transfer_status"),
    [
        ("local", WorkOrderStatus.RESOURCE_AVAILABLE.value, None),
        ("received", WorkOrderStatus.WAITING_FOR_RESOURCE.value,
         TransferStatus.RECEIVED.value),
        ("in_progress", WorkOrderStatus.IN_PROGRESS.value, None),
    ],
)
def test_selected_subset_protects_unselected_work_order_commitments(
    monkeypatch, commitment, status, transfer_status,
):
    state = _state(monkeypatch)
    # Bravo's only FP-102 unit is already committed to an omitted work order.
    _inventory(state, "bravo", "FP-102", 1)
    if commitment == "in_progress":
        # The normal started-maintenance path physically reserves the unit.
        _inventory(state, "bravo", "FP-102", 1, reserved=1)
    omitted = _wo("WO-OMITTED", "A28", "bravo", status=status,
                  resource_reserved=(commitment == "in_progress"))
    selected = _wo("WO-SELECTED", "A17", "alpha")
    state["work_orders"] = [selected, omitted]
    if transfer_status:
        state["transfers"] = [{
            "id": "T-RECEIVED", "work_order_id": omitted["id"],
            "part_number": "FP-102", "source_base": "charlie",
            "dest_base": "bravo", "quantity": 1, "status": transfer_status,
        }]

    result = planning_service.allocation_preview([selected["id"]])

    assert _allocation(result, selected["id"])["allocation_status"] == "NO_FEASIBLE_SOURCE"
    effect = next(row for row in result["inventory_effects"]
                  if row["base_id"] == "bravo" and row["part_number"] == "FP-102")
    assert effect["planned_units_claimed"] in {0, 1}
    assert effect["virtual_available_for_transfer_after_plan"] == 0


def test_local_stock_at_minimum_reserve_is_not_usable(monkeypatch):
    state = _state(monkeypatch)
    wo = _wo("WO-LOCAL", "A17", "alpha")
    state["work_orders"] = [wo]
    _inventory(state, "alpha", "FP-102", 1, reserve=1)

    result = planning_service.allocation_preview([wo["id"]])

    assert _allocation(result, wo["id"])["allocation_status"] == "NO_FEASIBLE_SOURCE"
    assert _allocation(result, wo["id"])["local_quantity_available_before"] == 0


def test_below_minimum_condition_local_and_received_stock_are_not_serviceable(monkeypatch):
    state = _state(monkeypatch)
    local_wo = _wo("WO-LOCAL", "A17", "alpha")
    received_wo = _wo("WO-RECEIVED", "A28", "bravo")
    state["work_orders"] = [local_wo, received_wo]
    _inventory(state, "alpha", "FP-102", 1, condition=34)
    _inventory(state, "bravo", "FP-102", 1, condition=34)
    state["transfers"] = [{
        "id": "T-RECEIVED", "work_order_id": received_wo["id"],
        "part_number": "FP-102", "source_base": "charlie",
        "dest_base": "bravo", "quantity": 1, "status": TransferStatus.RECEIVED.value,
    }]

    result = planning_service.allocation_preview()

    assert _allocation(result, local_wo["id"])["allocation_status"] == "NO_FEASIBLE_SOURCE"
    received = _allocation(result, received_wo["id"])
    assert received["allocation_status"] == "RECEIVED_RESOURCE_NOT_AVAILABLE"
    assert any(conflict.get("reason") == "RECEIVED_RESOURCE_BELOW_MINIMUM_CONDITION"
               for conflict in result["conflicts"])


def test_in_transit_is_not_debited_twice_and_pending_claim_is_provisional(monkeypatch):
    state = _state(monkeypatch)
    # In transit has already been physically debited at source.
    _inventory(state, "alpha", "FP-102", 0)
    _inventory(state, "bravo", "FP-102", 0)
    _inventory(state, "charlie", "FP-102", 1)
    in_transit = _wo("WO-TRANSIT", "A17", "alpha")
    pending_target = _wo("WO-PENDING", "A28", "bravo")
    state["work_orders"] = [in_transit, pending_target]
    state["transfers"] = [
        {"id": "T-IN", "work_order_id": in_transit["id"], "part_number": "FP-102",
         "source_base": "bravo", "dest_base": "alpha", "quantity": 1,
         "status": TransferStatus.IN_TRANSIT.value},
        {"id": "T-PENDING", "work_order_id": None, "part_number": "FP-102",
         "source_base": "charlie", "dest_base": "alpha", "quantity": 1,
         "status": TransferStatus.PENDING_APPROVAL.value},
    ]

    result = planning_service.allocation_preview()

    assert _allocation(result, in_transit["id"])["allocation_status"] == "EXISTING_IN_TRANSIT"
    assert _allocation(result, pending_target["id"])["allocation_status"] == "NO_FEASIBLE_SOURCE"
    source_effect = next(row for row in result["inventory_effects"]
                         if row["base_id"] == "charlie" and row["part_number"] == "FP-102")
    assert source_effect["planned_units_claimed"] == 1
    assert source_effect["overallocated_units"] == 0


@pytest.mark.parametrize(
    ("quantity", "reserved", "minimum_reserve", "condition", "expected"),
    [
        (1, 0, 1, 90, False),  # physically present but protected by reserve
        (1, 0, 0, 34, False),  # free, but below FP-102 serviceability threshold
        (2, 0, 1, 90, True),   # one usable unit remains above reserve
    ],
)
def test_local_availability_matches_maintenance_start_constraints(
    monkeypatch, quantity, reserved, minimum_reserve, condition, expected,
):
    from app.repositories import InventoryRepository
    from app.services.resource_service import local_availability

    monkeypatch.setattr(InventoryRepository, "find", lambda *_args: {
        "id": "inv-local", "quantity": quantity, "reserved": reserved,
        "minimum_reserve": minimum_reserve, "condition_pct": condition,
    })

    result = local_availability({"base_id": "alpha", "required_component": "FP-102"})

    assert result["available"] is expected


def test_start_and_approval_reject_below_minimum_condition_without_mutation(monkeypatch):
    from app.services import maintenance_service, transfer_service
    from app.repositories import InventoryRepository, TransferRepository, WorkOrderRepository

    inv = {"id": "inv-low", "quantity": 1, "reserved": 0,
           "minimum_reserve": 0, "condition_pct": 34}
    work_order = _wo("WO-LOW", "A17", "alpha", status=WorkOrderStatus.RESOURCE_AVAILABLE.value)
    monkeypatch.setattr(WorkOrderRepository, "get", lambda _work_order_id: work_order)
    monkeypatch.setattr(InventoryRepository, "find", lambda *_args: inv)
    with pytest.raises(maintenance_service.MaintenanceTransitionError, match="condition"):
        maintenance_service.start_maintenance(work_order["id"])

    transfer = {"id": "T-LOW", "status": TransferStatus.PENDING_APPROVAL.value,
                "source_base": "bravo", "dest_base": "alpha", "part_number": "FP-102",
                "quantity": 1, "work_order_id": None}
    monkeypatch.setattr(TransferRepository, "get", lambda _transfer_id: transfer)
    monkeypatch.setattr(TransferRepository, "active_for_work_order", lambda _work_order_id: None)
    with pytest.raises(transfer_service.TransferError, match="minimum serviceable condition"):
        transfer_service.approve_transfer(transfer["id"])

    assert inv["quantity"] == 1 and inv["reserved"] == 0
    assert transfer["status"] == TransferStatus.PENDING_APPROVAL.value

