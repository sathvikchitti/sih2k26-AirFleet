"""Transfer request scope and role-binding regressions.

The demo role headers are caller claims, not authenticated principals. These
tests establish that the API applies its capability and base-scope policy
without allowing body/query actor fields to override a supplied role header.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import reset, snapshot


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


def test_base_manager_can_request_foreign_source_to_own_base_without_debit(client):
    before = snapshot()
    stock_before = {
        (row["base_id"], row["part_number"]): row["quantity"]
        for row in before["inventory"]
    }

    response = client.post(
        "/api/transfers",
        json={
            "part_number": "HP-204",
            "source_base": "bravo",
            "dest_base": "alpha",
            "quantity": 1,
        },
        headers={"X-Demo-Role": "base", "X-Demo-Base": "alpha"},
    )

    assert response.status_code == 200, response.text
    transfer = response.json()
    assert transfer["source_base"] == "bravo"
    assert transfer["dest_base"] == "alpha"
    assert transfer["status"] == "PENDING_APPROVAL"
    after = snapshot()
    assert len(after["transfers"]) == len(before["transfers"]) + 1
    assert after["audit"][-1]["event_type"] == "TRANSFER_CREATED"
    assert after["inventory"] == before["inventory"]
    assert {
        (row["base_id"], row["part_number"]): row["quantity"]
        for row in after["inventory"]
    } == stock_before


def test_base_manager_cannot_request_transfer_to_foreign_destination(client):
    before = snapshot()
    response = client.post(
        "/api/transfers",
        json={
            "part_number": "HP-204",
            "source_base": "bravo",
            "dest_base": "charlie",
            "quantity": 1,
        },
        headers={"X-Demo-Role": "base", "X-Demo-Base": "alpha"},
    )
    assert response.status_code == 403
    assert snapshot() == before


@pytest.mark.parametrize("headers", [
    {},
    {"X-Demo-Role": "base"},
    {"X-Demo-Role": "base", "X-Demo-Base": "unknown"},
    {"X-Demo-Role": "not-a-role", "X-Demo-Base": "alpha"},
])
def test_transfer_creation_requires_valid_role_and_base_claim(client, headers):
    before = snapshot()
    response = client.post(
        "/api/transfers",
        json={
            "part_number": "HP-204",
            "source_base": "bravo",
            "dest_base": "alpha",
            "quantity": 1,
        },
        headers=headers,
    )
    assert response.status_code == 403
    assert snapshot() == before


@pytest.mark.parametrize(("binding", "expected_detail"), [
    ("unknown_work_order", "unknown work order"),
    ("wrong_component", "component does not match"),
    ("wrong_destination", "destination base does not match"),
    ("wrong_aircraft", "aircraft does not match"),
    ("unknown_source", "source or destination base is invalid"),
    ("same_base", "source and destination must be different"),
])
def test_invalid_transfer_relationships_are_rejected_without_mutation(
    client, binding, expected_detail,
):
    from app.services.maintenance_service import create_manual_work_order

    work_order = create_manual_work_order("A17", "HP-204")
    assert work_order is not None
    payload = {
        "part_number": "HP-204",
        "source_base": "charlie",
        "dest_base": "alpha",
    }
    if binding == "unknown_work_order":
        payload["work_order_id"] = "WO-DOES-NOT-EXIST"
    elif binding == "wrong_component":
        payload.update(part_number="FP-102", work_order_id=work_order["id"])
    elif binding == "wrong_destination":
        payload.update(dest_base="bravo", work_order_id=work_order["id"])
    elif binding == "wrong_aircraft":
        payload.update(for_aircraft="A28", work_order_id=work_order["id"])
    elif binding == "unknown_source":
        payload.update(source_base="not-a-base")
    elif binding == "same_base":
        payload.update(source_base="alpha")

    before = snapshot()
    response = client.post(
        "/api/transfers",
        json=payload,
        headers={"X-Demo-Role": "logistics"},
    )
    assert response.status_code == 400, response.text
    assert expected_detail in response.json()["detail"]
    assert snapshot() == before


def test_base_manager_body_actor_cannot_escalate_approve_receive_or_cancel(client):
    before = snapshot()
    headers = {"X-Demo-Role": "base", "X-Demo-Base": "alpha"}

    approve = client.post(
        "/api/transfers/T-102/approve",
        json={"actor": "logistics"}, headers=headers,
    )
    receive = client.post(
        "/api/transfers/T-101/receive?actor=logistics", headers=headers,
    )
    cancel = client.post(
        "/api/transfers/T-102/cancel?actor=logistics", headers=headers,
    )

    assert [approve.status_code, receive.status_code, cancel.status_code] == [403, 403, 403]
    assert snapshot() == before
