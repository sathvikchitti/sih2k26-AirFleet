"""Permission-mode regressions for the caller-claimed demo role selector."""

import pytest
from fastapi.testclient import TestClient

from app import main
from app.repositories import snapshot, reset


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "hardened")
    monkeypatch.setenv("DEMO_RESET_ENABLED", "false")
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    reset()
    with TestClient(main.app) as instance:
        yield instance
    reset()


def test_hardened_default_requires_explicit_role_and_base_for_base_mutations(client):
    before = snapshot()
    no_role = client.patch("/api/inventory/inv-04", json={"quantity": 5})
    no_base = client.post(
        "/api/maintenance/work-orders?aircraft_id=A17",
        json={"component": "HP-204"}, headers={"X-Demo-Role": "base"},
    )
    wrong_base = client.post(
        "/api/maintenance/work-orders?aircraft_id=A17",
        json={"component": "HP-204"},
        headers={"X-Demo-Role": "base", "X-Demo-Base": "bravo"},
    )
    assert no_role.status_code == no_base.status_code == wrong_base.status_code == 403
    assert snapshot() == before


@pytest.mark.parametrize(("method", "path", "body", "query"), [
    ("post", "/api/aircraft/A17/predict", None, None),
    ("post", "/api/maintenance/events/PM-001/work-order", {"required_component": "HP-204"}, None),
    ("post", "/api/maintenance/events/PM-001/dismiss", None, None),
    ("post", "/api/maintenance/work-orders", {"component": "HP-204"}, {"aircraft_id": "A17"}),
    ("post", "/api/maintenance/work-orders/WO-1042/start", None, None),
    ("post", "/api/maintenance/work-orders/WO-1042/complete", None, None),
    ("post", "/api/maintenance/A17/start", None, None),
    ("post", "/api/maintenance/A17/complete", None, None),
    ("patch", "/api/inventory/inv-04", {"quantity": 5}, None),
    ("post", "/api/transfers", {"part_number": "HP-204", "source_base": "bravo",
                                  "dest_base": "alpha"}, None),
    ("post", "/api/transfers/T-101/approve", {}, None),
    ("post", "/api/transfers/T-101/receive", None, None),
    ("post", "/api/transfers/T-101/cancel", None, None),
    ("post", "/api/work-orders/WO-1042/recommendation/approve", {}, None),
    ("post", "/api/recommendations/A17/reject", {}, None),
    ("post", "/api/recommendations/A17/approve", {}, None),
])
def test_hardened_mutation_families_reject_missing_role_without_state_change(
    client, method, path, body, query,
):
    before = snapshot()
    request = getattr(client, method)
    response = request(path, json=body, params=query)
    assert response.status_code == 403, (path, response.text)
    assert snapshot() == before


def test_unknown_optional_base_claim_is_rejected_for_global_role(client):
    before = snapshot()
    response = client.patch(
        "/api/inventory/inv-04", json={"quantity": 5},
        headers={"X-Demo-Role": "logistics", "X-Demo-Base": "unknown"},
    )
    assert response.status_code == 403
    assert snapshot() == before


def test_present_role_header_wins_over_privileged_legacy_actor(client):
    before = snapshot()
    response = client.post(
        "/api/recommendations/A17/reject",
        json={"actor": "commander", "reason": "should not authorize"},
        headers={"X-Demo-Role": "logistics"},
    )
    assert response.status_code == 403
    assert snapshot() == before


def test_reset_is_disabled_by_default_even_for_commander(client):
    before = snapshot()
    response = client.post("/api/demo/reset", headers={"X-Demo-Role": "commander"})
    assert response.status_code == 403
    assert snapshot() == before


def test_invalid_permission_mode_fails_configuration_validation(monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "hardend")
    with pytest.raises(RuntimeError, match="DEMO_PERMISSION_MODE"):
        main.validate_permission_config()


def test_permission_mode_defaults_to_hardened(monkeypatch):
    monkeypatch.delenv("DEMO_PERMISSION_MODE", raising=False)
    from app.security import permission_mode
    assert permission_mode() == "hardened"


def test_explicit_compat_mode_preserves_legacy_actor_and_reset_when_enabled(client, monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "compat")
    before = snapshot()
    patched = client.patch("/api/inventory/inv-04", json={"quantity": 5})
    assert patched.status_code == 200
    monkeypatch.setenv("DEMO_RESET_ENABLED", "true")
    reset_response = client.post("/api/demo/reset")
    assert reset_response.status_code == 200
    assert snapshot() != before


def test_compat_preserves_scope_for_present_base_role_header(client, monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "compat")
    before = snapshot()
    wrong = client.post(
        "/api/maintenance/work-orders?aircraft_id=A17",
        json={"component": "HP-204"},
        headers={"X-Demo-Role": "base", "X-Demo-Base": "bravo"},
    )
    missing = client.post(
        "/api/maintenance/work-orders?aircraft_id=A17",
        json={"component": "HP-204"}, headers={"X-Demo-Role": "base"},
    )
    partial = client.post(
        "/api/maintenance/work-orders?aircraft_id=A17",
        json={"component": "HP-204"}, headers={"X-Demo-Base": "bravo"},
    )
    assert wrong.status_code == missing.status_code == partial.status_code == 403
    assert snapshot() == before

    # Headerless legacy actor/default behavior is intentionally retained only
    # while compat mode is explicitly selected.
    legacy = client.post(
        "/api/maintenance/work-orders?aircraft_id=A17",
        json={"component": "HP-204", "actor": "base"},
    )
    assert legacy.status_code == 200
