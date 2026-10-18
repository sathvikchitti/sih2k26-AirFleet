"""Read-only, indicative cycle-based spares demand forecast."""

from __future__ import annotations

import math
from collections import defaultdict
from copy import deepcopy
from typing import Any

from ..data import BASES
from ..domain import knowledge
from ..repositories import PartRepository, snapshot
from ..services.ml import get_provider, predict_validated
from .planning_service import allocation_preview
from .resource_service import search_from_snapshot


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _probability_within_horizon(prediction: dict, horizon_cycles: float) -> tuple[float | None, str | None]:
    """Approximate P(RUL <= horizon), distinguishing missing from out-of-range."""
    if prediction.get("rul_unit") != "cycles":
        return None, "invalid_or_missing_cycle_prediction"
    values = (prediction.get("rul"), prediction.get("rul_std"),
              prediction.get("rul_low"), prediction.get("rul_high"))
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(float(value)) for value in values):
        return None, "invalid_or_missing_uncertainty"
    rul, std, low, high = (float(value) for value in values)
    if min(rul, std, low, high) < 0 or low > rul or high < rul or low > high:
        return None, "invalid_or_missing_uncertainty"
    # Predictions whose supplied uncertainty envelope cannot intersect the
    # forecast window do not contribute to expected demand.
    if low > horizon_cycles or high < 0:
        return None, "outside_horizon"
    if std == 0:
        return (1.0 if rul <= horizon_cycles else 0.0), None
    return min(1.0, max(0.0, _normal_cdf((horizon_cycles - rul) / std))), None


def _base_names() -> dict[str, str]:
    return {str(row["id"]): str(row["name"]) for row in BASES}


def forecast_resources(horizon_cycles: float = 30.0, *,
                       _state: dict[str, Any] | None = None,
                       _predictions: dict[str, dict] | None = None,
                       _provider_name: str | None = None) -> dict[str, Any]:
    """Forecast cycle-based demand without mutating repositories or audit."""
    if (isinstance(horizon_cycles, bool) or not isinstance(horizon_cycles, (int, float))
            or not math.isfinite(float(horizon_cycles)) or not 0 <= float(horizon_cycles) <= 10000):
        raise ValueError("horizon_cycles must be finite and between 0 and 10000")
    horizon_cycles = float(horizon_cycles)
    state = _state if _state is not None else snapshot()
    mapping, mapping_source = knowledge.fd001_engine_part_mapping()
    aircraft_rows = sorted(state.get("aircraft", []), key=lambda row: str(row.get("id", "")))
    if _predictions is None:
        provider = get_provider()
        provider_name = str(getattr(provider, "name", type(provider).__name__))
        predictions: dict[str, dict] = {}
        for aircraft in aircraft_rows:
            aircraft_id = str(aircraft.get("id") or "").upper()
            # Provider failures preserve the application's normal 503 contract;
            # never fill the shared planner with a fabricated risk prediction.
            predictions[aircraft_id] = predict_validated(provider, aircraft_id)
    else:
        predictions = {str(key).upper(): value for key, value in _predictions.items()}
        provider_name = _provider_name or "injected-provider"

    aircraft_by_id = {str(row.get("id") or "").upper(): row for row in aircraft_rows}
    base_name = _base_names()
    parts = [row for row in state.get("parts", [])
             if str(row.get("category", "")).casefold() == "engine"]
    part_numbers = sorted({str(row["part_number"]).upper() for row in parts})
    part_by_number = {str(row["part_number"]).upper(): row for row in parts}
    mapping = {engine_id: component for engine_id, component in mapping.items()
               if component in part_by_number}

    # Open work orders already represent actionable demand. Do not count the
    # same aircraft/component again as a future probabilistic request.
    open_work_orders = [row for row in state.get("work_orders", [])
                        if row.get("status") in {
                            "OPEN", "WAITING_FOR_RESOURCE", "RESOURCE_AVAILABLE",
                            "SCHEDULED", "IN_PROGRESS",
                        }]
    active_aircraft_component = {
        (str(row.get("aircraft_id") or "").upper(),
         str(row.get("required_component") or "").upper())
        for row in open_work_orders if row.get("required_component")
    }

    component_aircraft: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    eligible_prediction_count = 0
    unavailable_prediction_count = 0
    outside_horizon_prediction_count = 0
    unmapped_prediction_count = 0
    model_versions: set[str] = set()
    aircraft_components: dict[str, str] = {}
    prediction_exclusions: dict[str, str] = {}
    horizon_suggestion_candidates: list[dict] = []
    for aircraft_id, aircraft in aircraft_by_id.items():
        prediction = predictions.get(aircraft_id)
        if not isinstance(prediction, dict):
            unavailable_prediction_count += 1
            continue
        metadata = prediction.get("metadata")
        engine_id = metadata.get("engine_id") if isinstance(metadata, dict) else None
        try:
            engine_id = int(engine_id)
        except (TypeError, ValueError):
            if prediction.get("rul_unit") == "cycles":
                unmapped_prediction_count += 1
            else:
                unavailable_prediction_count += 1
            continue
        component = mapping.get(engine_id)
        if component is None:
            unmapped_prediction_count += 1
            continue
        aircraft_components[aircraft_id] = component
        model_version = prediction.get("model_version")
        if isinstance(model_version, str):
            model_versions.add(model_version)
        if (aircraft_id, component) in active_aircraft_component:
            prediction_exclusions[aircraft_id] = "covered_by_open_work_order"
            continue
        # Keep only the same mapped, non-work-order-covered predictions that
        # can contribute to the active forecast. Larger-horizon suggestions
        # reuse these already-fetched values; they never call the provider or
        # rerun forecast_resources recursively.
        horizon_suggestion_candidates.append(prediction)
        probability, exclusion = _probability_within_horizon(prediction, horizon_cycles)
        if probability is None:
            prediction_exclusions[aircraft_id] = str(exclusion)
            if exclusion == "outside_horizon":
                outside_horizon_prediction_count += 1
            else:
                unavailable_prediction_count += 1
            continue
        eligible_prediction_count += 1
        base_id = str(aircraft.get("base_id") or "")
        component_aircraft[base_id][component].append({
            "aircraft_id": aircraft_id,
            "rul_cycles": float(prediction["rul"]),
            "rul_std": float(prediction["rul_std"]),
            "rul_low": float(prediction["rul_low"]),
            "rul_high": float(prediction["rul_high"]),
            "probability_within_horizon": probability,
            "provider_failure_probability": prediction.get("failure_probability"),
            "source": prediction.get("source"),
            "model_version": prediction.get("model_version"),
            "demand_basis": "indicative_cycle_rul_only",
        })

    suggested_horizon_cycles = None
    if eligible_prediction_count == 0:
        for tested_horizon in (60, 100, 125):
            if tested_horizon <= horizon_cycles:
                continue
            if any(_probability_within_horizon(prediction, tested_horizon)[0] is not None
                   for prediction in horizon_suggestion_candidates):
                suggested_horizon_cycles = tested_horizon
                break

    # Reuse the planner's read-only commitment ledger. It accounts for
    # pending donor claims and all open work-order local/received reservations.
    commitment_plan = allocation_preview(
        None, allocate_new=True, _state=state, _predictions=predictions,
    )
    inventory_by_key = {
        (str(row.get("base_id", "")).lower(), str(row.get("part_number", "")).upper()):
            deepcopy(row)
        for row in state.get("inventory", [])
    }
    for effect in commitment_plan.get("inventory_effects", []):
        key = (str(effect.get("base_id", "")).lower(),
               str(effect.get("part_number", "")).upper())
        inv = inventory_by_key.get(key)
        if inv is not None:
            inv["quantity"] = int(effect.get("virtual_quantity_after_plan", 0))

    # This immutable view represents physical stock remaining after existing
    # commitments. Proposed forecast moves use a separate, sequential ledger.
    committed_inventory = deepcopy(inventory_by_key)
    suggestion_inventory = deepcopy(inventory_by_key)

    # Reserve a virtual planning hold for each base's own future demand before
    # considering it as a donor. The hold lives only in the cloned suggestion
    # ledger; the reported stock and repositories remain unchanged.
    forecast_protection_by_key: dict[tuple[str, str], int] = {}
    for key, inv in suggestion_inventory.items():
        base_id, component = key
        demand_rows = component_aircraft.get(base_id, {}).get(component, [])
        expected_demand = sum(row["probability_within_horizon"] for row in demand_rows)
        quantity = max(0, int(inv.get("quantity", 0) or 0))
        reserved = max(0, int(inv.get("reserved", 0) or 0))
        minimum = max(0, int(inv.get("minimum_reserve", 0) or 0))
        condition = inv.get("condition_pct")
        min_condition = PartRepository.min_condition_pct(component)
        serviceable = (quantity > 0 and condition is not None
                       and float(condition) >= min_condition)
        uncommitted = max(0, quantity - reserved - minimum) if serviceable else 0
        protected = min(uncommitted, math.ceil(expected_demand)) if expected_demand > 0 else 0
        forecast_protection_by_key[key] = protected
        # search_from_snapshot and donor debits both consult `reserved`, so an
        # added virtual reserve prevents exports of locally protected units.
        inv["reserved"] = reserved + protected

    # Existing unbound inbound moves count as planned supply for forecast
    # demand. Shipments earmarked for an open WO/aircraft remain dedicated to
    # that need and are never subtracted from future demand.
    incoming_by_key: dict[tuple[str, str], int] = defaultdict(int)
    planned_work_order_inbound_by_key: dict[tuple[str, str], int] = defaultdict(int)
    for allocation in commitment_plan.get("allocations", []):
        if allocation.get("allocation_status") != "PROPOSED_REMOTE_TRANSFER":
            continue
        component = str(allocation.get("required_component") or "").upper()
        dest = str(allocation.get("destination_base") or "").lower()
        if component in part_by_number and dest in base_name:
            # The shared planner has provisionally assigned one donor unit to
            # this existing WO. Report it separately; it does not cover new
            # aircraft/component forecast demand.
            planned_work_order_inbound_by_key[(dest, component)] += 1
    active_statuses = {"PENDING_APPROVAL", "IN_TRANSIT"}
    inbound_supply_ledger = deepcopy(committed_inventory)
    open_work_order_ids = {str(row.get("id") or "").upper() for row in open_work_orders}
    ordered_transfers = sorted(state.get("transfers", []),
                               key=lambda row: (str(row.get("created") or row.get("created_at") or ""),
                                                str(row.get("id") or "")))
    for transfer in ordered_transfers:
        if transfer.get("status") not in active_statuses:
            continue
        component = str(transfer.get("part_number") or "").upper()
        dest = str(transfer.get("dest_base") or transfer.get("destination_base") or "").lower()
        part = part_by_number.get(component)
        if not part or dest not in base_name:
            continue
        # Shipment quantities linked to active WOs are earmarked for those
        # existing needs, not free future forecast supply. Keep them visible
        # as a separate informational count below.
        linked_wo_id = str(transfer.get("work_order_id") or "").upper()
        linked_active_wo = any(str(row.get("id") or "").upper() == linked_wo_id
                               for row in open_work_orders)
        dedicated_aircraft = bool(transfer.get("for_aircraft"))
        if linked_active_wo or dedicated_aircraft:
            continue
        ledger_inv = inbound_supply_ledger.get((dest, component))
        if ledger_inv is None:
            ledger_inv = {
                "base_id": dest, "part_number": component, "quantity": 0,
                "reserved": 0, "minimum_reserve": 0, "condition_pct": 0,
            }
            inbound_supply_ledger[(dest, component)] = ledger_inv
        qty = int(transfer.get("quantity", 1))
        incoming_condition = transfer.get("condition_pct")
        if (isinstance(incoming_condition, bool) or not isinstance(incoming_condition, (int, float))
                or not math.isfinite(float(incoming_condition))):
            continue
        before_qty = int(ledger_inv.get("quantity", 0))
        before_cond = int(ledger_inv.get("condition_pct", 0))
        projected_condition = (min(before_cond, int(incoming_condition)) if before_qty > 0
                               else int(incoming_condition))
        reserved = int(ledger_inv.get("reserved", 0))
        minimum = int(ledger_inv.get("minimum_reserve", 0))
        if projected_condition >= PartRepository.min_condition_pct(component):
            free_before = max(0, before_qty - reserved - minimum)
            free_after = max(0, before_qty + qty - reserved - minimum)
            incoming_by_key[(dest, component)] += free_after - free_before
            ledger_inv["quantity"] = before_qty + qty
            ledger_inv["condition_pct"] = projected_condition

    # Suggestions compete through a single cloned ledger; each donor unit can
    # be suggested at most once across the whole fleet response.
    bases = [row for row in BASES]
    result_bases = []
    all_suggestions = []
    for base in bases:
        base_id = str(base["id"])
        component_rows = []
        for component in part_numbers:
            part = part_by_number[component]
            original = next((row for row in state.get("inventory", [])
                             if str(row.get("base_id", "")).lower() == base_id.lower()
                             and str(row.get("part_number", "")).upper() == component), None)
            inv = committed_inventory.get((base_id.lower(), component))
            on_hand = int(original.get("quantity", 0)) if original else 0
            reserved = int(original.get("reserved", 0)) if original else 0
            minimum = int(original.get("minimum_reserve", 0)) if original else 0
            condition = int(original.get("condition_pct", 0)) if original else None
            min_condition = PartRepository.min_condition_pct(component)
            raw_transferable = max(0, on_hand - reserved - minimum)
            available_now = (raw_transferable if on_hand > 0 and condition is not None
                             and condition >= min_condition else 0)
            committed_qty = int(inv.get("quantity", 0)) if inv else 0
            committed_transferable = max(0, committed_qty - reserved - minimum)
            committed_available = (committed_transferable if committed_qty > 0
                                   and int(inv.get("condition_pct", 0)) >= min_condition else 0)
            aircraft_demand = component_aircraft.get(base_id, {}).get(component, [])
            expected = sum(row["probability_within_horizon"] for row in aircraft_demand)
            demand_status = "available" if aircraft_demand else "no_eligible_predictions"
            shortfall = (max(0, math.ceil(expected) - committed_available
                             - incoming_by_key[(base_id.lower(), component)])
                         if aircraft_demand else None)

            moves = []
            remaining = int(shortfall or 0)
            if aircraft_demand and remaining > 0:
                feasibility = search_from_snapshot(
                    {"base_id": base_id, "required_component": component,
                     "aircraft_id": aircraft_demand[0]["aircraft_id"]},
                    list(suggestion_inventory.values()),
                )
                candidates = sorted(
                    (row for row in feasibility.get("candidates", []) if row.get("feasible")),
                    key=lambda row: (float(row.get("eta_hours") or 0),
                                     float(row.get("distance_km") or 0),
                                     str(row.get("base_id") or "")),
                )
                for candidate in candidates:
                    if remaining <= 0:
                        break
                    source = str(candidate["base_id"]).lower()
                    donor = suggestion_inventory.get((source, component))
                    if donor is None:
                        continue
                    donor_available = max(
                        0, int(donor.get("quantity", 0)) - int(donor.get("reserved", 0))
                        - int(donor.get("minimum_reserve", 0)),
                    )
                    quantity = min(remaining, donor_available)
                    if quantity <= 0:
                        continue
                    move = {
                        "part_number": component,
                        "source_base": candidate["base_id"],
                        "destination_base": base_id,
                        "quantity": quantity,
                        "eta_hours": candidate["eta_hours"],
                        "distance_km": candidate["distance_km"],
                        "condition_pct": candidate["condition_pct"],
                        "min_condition_pct": candidate["min_condition_pct"],
                        "feasible": True,
                        "action": "create_transfer",
                    }
                    moves.append(move)
                    all_suggestions.append(move)
                    donor["quantity"] = int(donor.get("quantity", 0)) - quantity
                    remaining -= quantity

            component_rows.append({
                "component": component,
                "part_name": part.get("name", component),
                "demand_status": demand_status,
                "eligible_aircraft_count": len(aircraft_demand),
                "unavailable_aircraft_count": sum(
                    1 for aircraft_id, assigned in aircraft_components.items()
                    if assigned == component and aircraft_by_id[aircraft_id].get("base_id") == base_id
                    and prediction_exclusions.get(aircraft_id) in {
                        "invalid_or_missing_uncertainty", "invalid_or_missing_cycle_prediction",
                    }
                ),
                "outside_horizon_aircraft_count": sum(
                    1 for aircraft_id, assigned in aircraft_components.items()
                    if assigned == component and aircraft_by_id[aircraft_id].get("base_id") == base_id
                    and prediction_exclusions.get(aircraft_id) == "outside_horizon"
                ),
                "eligible_aircraft": aircraft_demand,
                "on_hand": on_hand,
                "reserved": reserved,
                "minimum_reserve": minimum,
                "condition_pct": condition,
                "min_condition_pct": min_condition,
                "available_for_transfer": available_now,
                "committed_available_for_transfer": committed_available,
                "forecast_protected_units": forecast_protection_by_key.get(
                    (base_id.lower(), component), 0,
                ),
                "inbound_pending_or_in_transit": incoming_by_key[(base_id.lower(), component)],
                "inbound_proposed_for_open_work_orders": planned_work_order_inbound_by_key[(base_id.lower(), component)],
                "inbound_work_order_committed": sum(
                    int(row.get("quantity", 1)) for row in state.get("transfers", [])
                    if row.get("status") in active_statuses
                    and str(row.get("part_number") or "").upper() == component
                    and str(row.get("dest_base") or row.get("destination_base") or "").lower() == base_id.lower()
                    and (str(row.get("work_order_id") or "").upper() in open_work_order_ids
                         or bool(row.get("for_aircraft")))
                ),
                "expected_demand": expected if aircraft_demand else None,
                "projected_shortfall": shortfall,
                "suggested_moves": moves,
            })
        result_bases.append({"base_id": base_id, "base_name": base["name"],
                             "components": component_rows})

    return {
        "forecast_status": "available" if eligible_prediction_count else "no_eligible_predictions",
        "horizon_cycles": horizon_cycles,
        "suggested_horizon_cycles": suggested_horizon_cycles,
        "provider": provider_name,
        "model_version": next(iter(model_versions)) if len(model_versions) == 1 else None,
        "mapping": {
            "label": "assumed mapping for demo",
            "source": mapping_source,
            "engine_to_component": {str(key): value for key, value in sorted(mapping.items())},
        },
        "demand_method": "indicative uncalibrated normal approximation using cycle RUL mean/std; P(RUL <= horizon)",
        "eligible_prediction_count": eligible_prediction_count,
        "unavailable_prediction_count": unavailable_prediction_count,
        "outside_horizon_prediction_count": outside_horizon_prediction_count,
        "unmapped_prediction_count": unmapped_prediction_count,
        "excluded_open_work_order_count": sum(
            1 for aircraft_id, component in active_aircraft_component
            if aircraft_components.get(aircraft_id) == component
        ),
        "suggested_moves": all_suggestions,
        "bases": result_bases,
        "mutated_state": False,
        "assumptions": [
            "Only cycle-based RUL predictions with finite point, standard deviation, and bounds overlapping [0, horizon] are included.",
            "Normal-approximation demand is indicative and uncalibrated; it is not the provider failure_probability or a component diagnosis.",
            "FD001 engine-to-component assignments are explicit demo assumptions, not model output or engineering approval.",
            "Expected demand remains fractional; projected shortfall rounds required units up after existing work-order, transfer, and serviceable unbound inbound commitments.",
            "Donor suggestions are assigned sequentially by base/component on one shared cloned ledger; they are deterministic, not a global optimizer.",
            "Before donor suggestions, each base/component protects up to ceil(expected future demand) from its current serviceable uncommitted stock on a cloned planning ledger only; this is not an inventory reservation and does not change reported stock.",
            "Inbound shipments linked to an open work order or aircraft remain earmarked for that existing need and do not reduce future probabilistic demand.",
            "Suggestions do not create, approve, reserve, or move a transfer; live transfer creation revalidates current state and permissions.",
        ],
    }
