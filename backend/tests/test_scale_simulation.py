from copy import deepcopy
import json
import random

import pytest

from app.evaluation import scale_simulation
from app.main import app
from app.routers import evaluation as evaluation_router
from app.repositories import snapshot
from app.services.planning_service import allocation_preview
from app.services.resource_service import ResourceContext, search_from_snapshot


def _tiny_context():
    return ResourceContext(
        bases=(("home", "Home"), ("donor", "Donor"), ("far", "Far")),
        parts=(("P-1", "Part One", 50),),
        routes=(("home", "donor", 100.0, 2.0), ("home", "far", 300.0, 6.0),
                ("donor", "far", 250.0, 5.0)),
    )


def _tiny_state():
    return {
        "aircraft": [
            {"id": "A1", "base_id": "home", "status": "WAITING_FOR_PART"},
            {"id": "A2", "base_id": "home", "status": "WAITING_FOR_PART"},
        ],
        "parts": [{"part_number": "P-1", "min_condition_pct": 50}],
        "inventory": [
            {"id": "H1", "base_id": "home", "part_number": "P-1", "quantity": 0,
             "reserved": 0, "minimum_reserve": 0, "condition_pct": 0},
            {"id": "D1", "base_id": "donor", "part_number": "P-1", "quantity": 2,
             "reserved": 0, "minimum_reserve": 1, "condition_pct": 80},
            {"id": "F1", "base_id": "far", "part_number": "P-1", "quantity": 1,
             "reserved": 0, "minimum_reserve": 1, "condition_pct": 90},
        ],
        "work_orders": [
            {"id": "WO-OLD", "aircraft_id": "A1", "base_id": "home", "required_component": "P-1",
             "status": "WAITING_FOR_RESOURCE", "priority": "LOW", "created_at": "2026-01-01T00:00:00Z",
             "estimated_repair_hours": 8, "resource_reserved": False},
            {"id": "WO-NEW", "aircraft_id": "A2", "base_id": "home", "required_component": "P-1",
             "status": "WAITING_FOR_RESOURCE", "priority": "CRITICAL", "created_at": "2026-01-02T00:00:00Z",
             "estimated_repair_hours": 8, "resource_reserved": False},
        ],
        "transfers": [],
    }


def _tiny_predictions():
    return {aircraft_id: {"risk_level": "LOW", "rul": None, "rul_unit": "cycles",
                          "subsystem": None, "predicted_issue": None}
            for aircraft_id in ("A1", "A2")}


def test_resource_context_searches_only_its_immutable_catalog_and_routes():
    context = scale_simulation.RESOURCE_CONTEXT
    state, _ = scale_simulation._generate_scenario(0)
    order = state["work_orders"][0]
    before = deepcopy(state)
    found = search_from_snapshot(order, state["inventory"], resource_context=context)
    assert len(found["bases_searched"]) == 6
    assert len(found["candidates"]) + len(found["infeasible"]) == 5
    assert found["required_component"].startswith("SIM-")
    assert state == before
    assert isinstance(context.bases, tuple) and isinstance(context.parts, tuple) and isinstance(context.routes, tuple)


def test_nearest_fcfs_random_and_local_procurement_share_constraints_without_mutation():
    context = _tiny_context()
    state = _tiny_state()
    before = deepcopy(state)
    predictions = _tiny_predictions()
    common = {"_state": state, "_predictions": predictions, "resource_context": context,
              "procurement_lead_hours": 12.0}

    proposed = allocation_preview(source_policy="proposed", **common)
    nearest = allocation_preview(source_policy="nearest_feasible", order_policy="first_come_first_served", **common)
    random_a = allocation_preview(source_policy="random_feasible", _rng=random.Random(7), **common)
    random_b = allocation_preview(source_policy="random_feasible", _rng=random.Random(7), **common)
    local_only = allocation_preview(source_policy="local_only_procurement", **common)

    proposed_sources = {row["work_order_id"]: row["allocation_status"]
                        for row in proposed["allocations"]}
    nearest_sources = {row["work_order_id"]: row["allocation_status"]
                       for row in nearest["allocations"]}
    local_rows = {row["work_order_id"]: row for row in local_only["allocations"]}
    assert proposed_sources["WO-NEW"] == "PROPOSED_REMOTE_TRANSFER"
    assert proposed_sources["WO-OLD"] == "PROPOSED_LOCAL_PROCUREMENT"
    assert nearest_sources["WO-OLD"] == "PROPOSED_REMOTE_TRANSFER"
    assert nearest_sources["WO-NEW"] == "PROPOSED_LOCAL_PROCUREMENT"
    assert all(row["allocation_status"] != "PROPOSED_REMOTE_TRANSFER"
               for row in local_only["allocations"])
    assert all(row["allocation_status"] == "PROPOSED_LOCAL_PROCUREMENT"
               for row in local_only["allocations"])
    assert all(row["procurement_eta_hours"] == 12.0 for row in local_rows.values())
    assert [row["source_base"] for row in random_a["allocations"]] == [
        row["source_base"] for row in random_b["allocations"]
    ]
    assert all(effect["overallocated_units"] == 0 for effect in proposed["inventory_effects"])
    assert all(effect["overallocated_units"] == 0 for effect in nearest["inventory_effects"])
    for plan in (proposed, nearest, random_a):
        for row in plan["allocations"]:
            if row["allocation_status"] == "PROPOSED_REMOTE_TRANSFER":
                assert any(candidate["feasible"] and candidate["source_base"] == row["source_base"]
                           for candidate in row["candidates"])
        assert all(effect["overallocated_units"] == 0 for effect in plan["inventory_effects"])
    assert state == before


@pytest.mark.parametrize("lead", [True, float("nan"), float("inf"), -1.0])
def test_invalid_procurement_lead_is_rejected(lead):
    with pytest.raises(ValueError, match="finite nonnegative"):
        allocation_preview(procurement_lead_hours=lead, _state=_tiny_state(),
                           _predictions=_tiny_predictions(), resource_context=_tiny_context())


def test_scale_summary_runs_300_repeatable_paired_scenarios_and_preserves_live_store():
    before = snapshot()
    first = scale_simulation.run_scale_simulation()
    after = snapshot()
    second = scale_simulation.run_scale_simulation()

    assert first["scenario_count"] == 300
    assert first["scenario_fingerprint"] == second["scenario_fingerprint"]
    assert first["config_fingerprint"] == second["config_fingerprint"]
    assert first["policies"] == second["policies"]
    assert first["scenario_results"] == second["scenario_results"]
    assert after == before
    assert set(first["policies"]) == {
        "proposed", "nearest_fcfs", "random_feasible", "local_only_procurement",
    }
    assert len(first["scenario_results"]) == 300
    assert first["scenario_results"][0]["aircraft_count"] == 40
    assert first["scenario_results"][0]["active_work_order_count"] == 12
    assert set(first["input_scarcity_summary"]) == {number for number, _, _ in scale_simulation.PARTS}
    for number, *_ in scale_simulation.PARTS[:6]:
        scarcity = first["input_scarcity_summary"][number]
        assert scarcity["scenarios_with_competing_demand"] == 300
        assert 0 <= scarcity["scenarios_with_supply_limited_competing_demand"] <= 300
        assert 0 <= scarcity["scenarios_with_no_serviceable_supply"] <= 300
    for number, *_ in scale_simulation.PARTS[6:]:
        assert first["input_scarcity_summary"][number]["scenarios_with_demand"] == 0
    for policy in first["policies"].values():
        assert policy["scenario_count"] == 300
        assert policy["availability_pct_ci95"]["lower"] <= policy["availability_pct_ci95"]["upper"]
        assert policy["summed_censored_aircraft_hours_lost_ci95"]["lower"] <= policy["summed_censored_aircraft_hours_lost_ci95"]["upper"]
        assert policy["unserved_rate_ci95"]["lower"] <= policy["unserved_rate_ci95"]["upper"]
    for scenario in first["scenario_results"]:
        for metrics in scenario["policy_metrics"].values():
            assert metrics["available_aircraft_hours"] + metrics["summed_censored_aircraft_hours_lost"] == 40 * 48
    assert "real_operational_performance_claimed" in first and first["real_operational_performance_claimed"] is False
    assert "cycle counts are not converted to hours" in " ".join(first["assumptions"])


def test_bootstrap_ci_is_repeatable_and_handles_empty_or_singleton_data():
    assert scale_simulation._bootstrap_ci([], random.Random(1)) == {"lower": None, "upper": None}
    assert scale_simulation._bootstrap_ci([4.5], random.Random(1)) == {"lower": 4.5, "upper": 4.5}
    assert scale_simulation._bootstrap_ci([1.0, 2.0, 3.0], random.Random(9)) == \
        scale_simulation._bootstrap_ci([1.0, 2.0, 3.0], random.Random(9))


def test_evaluation_get_route_is_registered_and_returns_reproducible_readonly_contract():
    before = snapshot()
    route = next(route for route in app.routes
                 if getattr(route, "path", None) == "/api/evaluation/summary")
    assert route.methods == {"GET"}
    result = evaluation_router.evaluation_summary()
    assert result["evaluation_type"] == "deterministic_synthetic_simulation"
    assert result["scenario_count"] == 300
    assert result["scenario_fingerprint"]
    assert set(result["policies"]) == set(scale_simulation.POLICIES)
    assert result["real_operational_performance_claimed"] is False
    assert "scenario_results" not in result
    assert len(json.dumps(result)) < 200_000
    assert scale_simulation.REPORT_JSON_PATH == (
        scale_simulation.Path(scale_simulation.__file__).resolve().parent
        / "results" / "scale_simulation.json"
    )
    assert set(result["component_summary"]) == set(scale_simulation.POLICIES)
    for policy_summary in result["component_summary"].values():
        assert len(policy_summary) == 8
        assert [policy_summary[number]["work_orders"] for number, _, _ in scale_simulation.PARTS] == [
            600, 600, 600, 600, 600, 600, 0, 0,
        ]
    assert snapshot() == before


def test_evaluation_get_uses_fixed_report_and_returns_503_when_missing(monkeypatch, tmp_path):
    from fastapi import HTTPException

    monkeypatch.setattr(evaluation_router, "REPORT_JSON_PATH", tmp_path / "missing.json")
    with pytest.raises(HTTPException) as exc:
        evaluation_router.evaluation_summary()
    assert exc.value.status_code == 503

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evaluation_router, "REPORT_JSON_PATH", invalid_path)
    with pytest.raises(HTTPException) as invalid:
        evaluation_router.evaluation_summary()
    assert invalid.value.status_code == 503

    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text(json.dumps({
        "evaluation_type": "deterministic_synthetic_simulation",
        "simulated": True,
        "real_operational_performance_claimed": False,
        "scenario_count": 300,
        "policies": None,
    }), encoding="utf-8")
    monkeypatch.setattr(evaluation_router, "REPORT_JSON_PATH", malformed_path)
    with pytest.raises(HTTPException) as malformed:
        evaluation_router.evaluation_summary()
    assert malformed.value.status_code == 503
