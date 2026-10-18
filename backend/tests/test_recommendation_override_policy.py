"""The Commander may choose among feasible candidates, never bypass hard filters."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import InventoryRepository, reset, snapshot
from app.services import maintenance_service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "hardened")
    monkeypatch.setenv("DEMO_RESET_ENABLED", "false")
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    reset()
    with TestClient(app) as instance:
        yield instance
    reset()


def _work_order():
    result = maintenance_service.create_manual_work_order("A19", "HP-204")
    assert result is not None
    return result


def test_commander_may_choose_an_alternate_feasible_candidate(client):
    work_order = _work_order()
    evaluation = client.get(f"/api/work-orders/{work_order['id']}/recommendation")
    assert evaluation.status_code == 200, evaluation.text
    candidates = evaluation.json()["candidates"]
    bases = [row["base_id"] for row in candidates]
    assert len(bases) >= 2
    alternate = next(base for base in bases if base != evaluation.json()["recommended"]["base_id"])

    response = client.post(
        f"/api/work-orders/{work_order['id']}/recommendation/approve",
        json={"donor_base": alternate},
        headers={"X-Demo-Role": "commander"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["transfer"]["source_base"] == alternate
    assert response.json()["transfer"]["dest_base"] == "alpha"
    assert response.json()["transfer"]["status"] == "IN_TRANSIT"


@pytest.mark.parametrize("constraint", ["reserve", "unavailable", "condition", "unknown_base"])
def test_commander_selection_cannot_bypass_infeasible_candidate_constraints(client, constraint):
    work_order = _work_order()
    donor = "charlie"
    inv = InventoryRepository.find(donor, "HP-204")
    if constraint == "reserve":
        InventoryRepository.update(inv["id"], minimum_reserve=inv["quantity"])
    elif constraint == "unavailable":
        InventoryRepository.update(inv["id"], quantity=0, reserved=0, minimum_reserve=0)
    elif constraint == "condition":
        InventoryRepository.update(inv["id"], condition_pct=0)
    elif constraint == "unknown_base":
        donor = "not-a-base"

    before = snapshot()
    response = client.post(
        f"/api/work-orders/{work_order['id']}/recommendation/approve",
        json={"donor_base": donor, "allow_reserve_override": True},
        headers={"X-Demo-Role": "commander"},
    )

    assert response.status_code == 400, response.text
    assert "not a feasible recommendation candidate" in response.json()["detail"]
    assert snapshot() == before
