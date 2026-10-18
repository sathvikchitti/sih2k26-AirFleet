"""Deterministic opt-in FD001 operations scenario integration tests."""

from __future__ import annotations

import pytest

from app import main
from app.data import BASES
from app.repositories import (
    AircraftRepository,
    EventRepository,
    InventoryRepository,
    TransferRepository,
    WorkOrderRepository,
    available_for_transfer,
    reset as reset_repositories,
    snapshot,
    store,
)
from app.services.availability_service import fleet_overview
from app.services.fd001_operations_scenario import scenario_manifest
from app.services.ml import get_provider, set_provider
from app.services.ml.mock_provider import MockMLProvider
from app.services.recommendation_service import evaluate_candidates


@pytest.fixture
def fd001_operations(monkeypatch):
    monkeypatch.setenv("ML_PROVIDER", "fd001")
    monkeypatch.setenv("DEMO_SCENARIO", "fd001_operations")
    monkeypatch.delenv("FD001_ENGINE_PART_MAPPING", raising=False)
    set_provider(None)
    main.initialize_demo_state()
    yield
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    set_provider(MockMLProvider())
    reset_repositories()


def _structural_signature() -> tuple:
    state = snapshot()
    return (
        tuple((a["id"], a["base_id"], a["status"]) for a in state["aircraft"]),
        tuple((e["id"], e["aircraft_id"], e["status"], e.get("work_order_id"))
              for e in state["predicted_events"]),
        tuple((w["id"], w["aircraft_id"], w["required_component"], w["status"],
               w.get("predicted_event_id"), w.get("resource_reserved"))
              for w in state["work_orders"]),
        tuple((t["id"], t["work_order_id"], t["status"], t["source_base"],
               t["dest_base"], t["part_number"]) for t in state["transfers"]),
        tuple((i["id"], i["base_id"], i["part_number"], i["quantity"], i["reserved"],
               i["minimum_reserve"], i["status"]) for i in state["inventory"]),
        tuple((row["aircraft_id"], round(float(row["rul"]), 8), row["rul_unit"],
               row.get("failure_probability"), row["is_synthetic"])
              for row in state["prediction_history"]),
        tuple((row["id"], row["event_type"], row["entity_type"], row["entity_id"])
              for row in state["audit"]),
    )


def test_fd001_scenario_covers_six_coherent_operational_cases(fd001_operations):
    manifest = main.demo_scenario()
    assert manifest["scenario_id"] == "fd001_operations_v1"
    assert manifest["operational_data_synthetic"] is True
    assert manifest["model_provider"] == "fd001-random-forest"
    assert manifest["model_version"] == "cmapss-fd001-rf-v1"
    assert [scenario["id"] for scenario in manifest["scenarios"]] == list("ABCDEF")
    assert len(AircraftRepository.list_all()) == 10
    assert len(BASES) == 3
    assert all(scenario["aircraft_id"] in AircraftRepository.all_ids()
               for scenario in manifest["scenarios"])

    aircraft = {row["id"]: row for row in AircraftRepository.list_all()}
    assert aircraft["A17"]["status"] == "AVAILABLE"  # low FD001 RUL risk, no open WO
    assert aircraft["A21"]["status"] == "WAITING_FOR_PART"
    assert aircraft["A28"]["status"] == "WAITING_FOR_PART"
    assert aircraft["A26"]["status"] == "MAINTENANCE"
    assert aircraft["A24"]["status"] == "DEGRADED"  # completion did not fake recovery
    assert aircraft["A32"]["status"] == "WAITING_FOR_PART"

    scenario_by_id = {row["id"]: row for row in manifest["scenarios"]}
    assert scenario_by_id["B"]["component_selection_source"] == "human_selected"
    assert scenario_by_id["C"]["next_action"] == "receive_in_transit_transfer"
    assert scenario_by_id["D"]["component_selection_source"] == "fixture_scenario"
    work_orders = {row["id"]: row for row in WorkOrderRepository.list_all()}
    events = {row["id"]: row for row in EventRepository.list_all()}
    transfers = {row["id"]: row for row in TransferRepository.list_all()}

    b = work_orders[scenario_by_id["B"]["work_order_id"]]
    c = work_orders[scenario_by_id["C"]["work_order_id"]]
    d = work_orders[scenario_by_id["D"]["work_order_id"]]
    e = work_orders[scenario_by_id["E"]["work_order_id"]]
    f = work_orders[scenario_by_id["F"]["work_order_id"]]
    assert b["aircraft_id"] == "A32" and b["status"] == "WAITING_FOR_RESOURCE"
    assert c["aircraft_id"] == "A21" and c["status"] == "WAITING_FOR_RESOURCE"
    assert d["aircraft_id"] == "A28" and d["required_component"] == "OE-310"
    assert e["aircraft_id"] == "A26" and e["status"] == "IN_PROGRESS"
    assert e["resource_reserved"] is True
    assert f["aircraft_id"] == "A24" and f["status"] == "COMPLETED"
    assert b["component_source"] == c["component_source"] == "human_selected"

    for work_order in (b, c):
        event = events[work_order["predicted_event_id"]]
        assert event["aircraft_id"] == work_order["aircraft_id"]
        assert event["subsystem"] is None
        assert event["rul_unit"] == "cycles"
        assert event["predicted_time"] is None

    candidate_eval = evaluate_candidates(c["id"])
    assert candidate_eval["recommended"]["source_base"] == "charlie"
    assert [row["reason"] for row in candidate_eval["rejected"]
            if row["base_id"] == "bravo"] == ["MINIMUM_RESERVE_VIOLATION"]
    assert transfers[scenario_by_id["C"]["transfer_id"]]["status"] == "IN_TRANSIT"
    assert transfers[scenario_by_id["C"]["transfer_id"]]["work_order_id"] == c["id"]

    no_source = evaluate_candidates(d["id"])
    assert no_source["recommended"] is None
    assert no_source["candidates"] == []
    assert {row["reason"] for row in no_source["rejected"]} == {"MINIMUM_RESERVE_VIOLATION"}
    assert transfers[scenario_by_id["F"]["transfer_id"]]["status"] == "RECEIVED"
    assert transfers[scenario_by_id["F"]["transfer_id"]]["part_number"] == "AV-077"

    # Every stock movement in the fixture has a workflow record. The one
    # remaining reservation is attached to the in-progress A26 order.
    reserved = [row for row in InventoryRepository.list_all() if row["reserved"]]
    assert [(row["base_id"], row["part_number"], row["reserved"])
            for row in reserved] == [("bravo", "FP-102", 1)]
    assert available_for_transfer(reserved[0]) == 0
    assert sum(row["quantity"] for row in InventoryRepository.find_all_for_part("AV-077")) == 2
    assert InventoryRepository.find("bravo", "AV-077")["quantity"] == 0
    assert InventoryRepository.find("alpha", "AV-077")["quantity"] == 1

    history = store()["prediction_history"]
    assert len(history) == 10
    assert all(row["rul_unit"] == "cycles" for row in history)
    assert all(row["failure_probability"] is None for row in history)
    assert all(row["is_synthetic"] is True for row in history)
    predictions = [get_provider().predict(aircraft_id) for aircraft_id in AircraftRepository.all_ids()]
    assert all(row["rul_unit"] == "cycles" and row["failure_probability"] is None
               and row["is_synthetic"] for row in predictions)

    fleet = fleet_overview()
    assert fleet["total"] == 10
    assert fleet["available"] == 4
    assert fleet["maintenance"] == 1
    assert fleet["waiting_for_part"] == 3
    assert fleet["at_risk"] == 2


def test_reinitializing_fd001_scenario_rebuilds_same_ids_and_state(fd001_operations):
    first_manifest = main.demo_scenario()
    first_state = _structural_signature()
    main.initialize_demo_state()
    second_manifest = main.demo_scenario()
    assert second_manifest["scenario_id"] == first_manifest["scenario_id"]
    assert second_manifest["scenarios"] == first_manifest["scenarios"]
    assert _structural_signature() == first_state
    assert len({row["id"] for row in WorkOrderRepository.list_all()}) == 5
    assert len({row["id"] for row in TransferRepository.list_all()}) == 2
    pairs = [(row["base_id"], row["part_number"]) for row in InventoryRepository.list_all()]
    assert len(pairs) == len(set(pairs))


def test_scenario_requires_fd001_without_resetting_mock_state(monkeypatch):
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.setenv("DEMO_SCENARIO", "fd001_operations")
    set_provider(MockMLProvider())
    before = _structural_signature()
    with pytest.raises(RuntimeError, match="requires ML_PROVIDER=fd001"):
        main.initialize_demo_state()
    assert _structural_signature() == before
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    reset_repositories()


def test_scenario_api_exposes_ui_inputs_and_reset_role_is_enforced(fd001_operations, monkeypatch):
    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        manifest_response = client.get("/api/demo/scenario")
        assert manifest_response.status_code == 200
        manifest = manifest_response.json()
        assert manifest["scenario_id"] == "fd001_operations_v1"

        aircraft_response = client.get("/api/aircraft")
        assert aircraft_response.status_code == 200
        aircraft = {row["id"]: row for row in aircraft_response.json()}
        assert aircraft["A21"]["health"]["rul_unit"] == "cycles"
        assert aircraft["A21"]["health"]["failure_probability"] is None
        assert aircraft["A21"]["health"]["is_synthetic"] is True
        assert aircraft["A21"]["health"]["required_component"] is None

        orders_response = client.get("/api/maintenance/work-orders")
        assert orders_response.status_code == 200
        orders = {row["id"]: row for row in orders_response.json()}
        c = next(row for row in manifest["scenarios"] if row["id"] == "C")
        d = next(row for row in manifest["scenarios"] if row["id"] == "D")
        assert orders[c["work_order_id"]]["component_source"] == "human_selected"
        assert orders[c["work_order_id"]]["active_transfer_id"] == c["transfer_id"]
        assert orders[d["work_order_id"]]["component_source"] == "fixture_scenario"

        demand_response = client.get("/api/resources/demand")
        assert demand_response.status_code == 200
        assert demand_response.json()

        d_response = client.get(f"/api/work-orders/{d['work_order_id']}/recommendation")
        assert d_response.status_code == 200
        assert d_response.json()["recommended"] is None
        assert d_response.json()["candidates"] == []
        assert {row["reason"] for row in d_response.json()["rejected"]} == {
            "MINIMUM_RESERVE_VIOLATION"
        }

        before_reset = _structural_signature()
        denied = client.post("/api/demo/reset", headers={
            "X-Demo-Role": "base", "X-Demo-Base": "alpha",
        })
        assert denied.status_code == 403
        assert _structural_signature() == before_reset

        monkeypatch.setenv("DEMO_RESET_ENABLED", "true")
        reset = client.post("/api/demo/reset", headers={"X-Demo-Role": "commander"})
        assert reset.status_code == 200
        assert client.get("/api/demo/scenario").json()["scenario_id"] == "fd001_operations_v1"
        after_reset = _structural_signature()
        assert after_reset[:6] == before_reset[:6]
        assert after_reset[6][-1][1] == "DEMO_RESET"
        assert sum(row[1] == "DEMO_RESET" for row in after_reset[6]) == 1


def test_default_mapping_forecast_suggestion_is_readonly_and_logistics_can_request_it(
        fd001_operations):
    from fastapi.testclient import TestClient

    before_forecast = snapshot()
    with TestClient(main.app) as client:
        response = client.get("/api/resources/forecast?horizon_cycles=60")
        assert response.status_code == 200
        forecast = response.json()

        assert forecast["forecast_status"] == "available"
        assert forecast["horizon_cycles"] == 60
        assert forecast["mapping"]["label"] == "assumed mapping for demo"
        assert forecast["mapping"]["source"] == "built_in_demo_assumption"
        assert forecast["mapping"]["engine_to_component"] == {
            str(engine_id): "HP-204" if engine_id % 2 else "OE-310"
            for engine_id in range(1, 11)
        }
        assert forecast["suggested_moves"]
        assert forecast["mutated_state"] is False

        # Every suggestion must fit the same frozen post-commitment, reserve,
        # condition, and forecast-protection ledger used by the API.
        component_rows = {
            (base["base_id"], component["component"]): component
            for base in forecast["bases"]
            for component in base["components"]
        }
        proposed_by_donor = {}
        for move in forecast["suggested_moves"]:
            assert move["feasible"] is True
            assert move["action"] == "create_transfer"
            assert move["quantity"] >= 1
            assert move["condition_pct"] >= move["min_condition_pct"]
            key = (move["source_base"], move["part_number"])
            proposed_by_donor[key] = proposed_by_donor.get(key, 0) + move["quantity"]
        for key, total_suggested in proposed_by_donor.items():
            source = component_rows[key]
            remaining_after_forecast_protection = max(
                0,
                source["committed_available_for_transfer"]
                - source["forecast_protected_units"],
            )
            assert total_suggested <= remaining_after_forecast_protection

        assert snapshot() == before_forecast

        move = forecast["suggested_moves"][0]
        transfer_request = {
            "part_number": move["part_number"],
            "source_base": move["source_base"],
            "dest_base": move["destination_base"],
            "quantity": move["quantity"],
            "actor": "logistics",
        }
        before_denied = snapshot()
        denied = client.post(
            "/api/transfers", json=transfer_request,
            headers={"X-Demo-Role": "commander"},
        )
        assert denied.status_code == 403
        assert snapshot() == before_denied

        before_created = snapshot()
        created = client.post(
            "/api/transfers", json=transfer_request,
            headers={"X-Demo-Role": "logistics"},
        )
        assert created.status_code == 200
        transfer = created.json()
        assert transfer["status"] == "PENDING_APPROVAL"
        assert transfer["part_number"] == move["part_number"]
        assert transfer["source_base"] == move["source_base"]
        assert transfer["dest_base"] == move["destination_base"]
        assert transfer["quantity"] == move["quantity"]

        after_created = snapshot()
        assert after_created["inventory"] == before_created["inventory"]
        assert after_created["work_orders"] == before_created["work_orders"]
        assert after_created["predicted_events"] == before_created["predicted_events"]
        assert after_created["transfers"][:-1] == before_created["transfers"]
        assert after_created["transfers"][-1]["id"] == transfer["id"]
        assert len(after_created["audit"]) == len(before_created["audit"]) + 1


def test_clean_fd001_reset_remains_separate_from_operations_fixture(monkeypatch):
    monkeypatch.setenv("ML_PROVIDER", "fd001")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    set_provider(None)
    main.initialize_demo_state()
    assert scenario_manifest()["scenario_id"] is None
    assert len(AircraftRepository.list_all()) == 10
    assert WorkOrderRepository.list_all() == []
    assert TransferRepository.list_all() == []
    assert len(store()["prediction_history"]) == 10
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    set_provider(MockMLProvider())
    reset_repositories()
