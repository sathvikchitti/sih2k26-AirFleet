"""Exercise restricted access through the actual API middleware and routes."""

import json

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app import main
from app.access import access_mode, frontend_origins, validate_access_config
from app.repositories import reset, snapshot

# Disposable test credentials, never deployment credentials.
PASSWORD = "disposable-test-password-only"
USERS = {
    "leader": {"password": PASSWORD, "role": "commander"},
    "supply": {"password": PASSWORD, "role": "logistics"},
    "alpha": {"password": PASSWORD, "role": "base", "base": "alpha"},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_MODE", "restricted")
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "hardened")
    monkeypatch.setenv("DEMO_BASIC_USERS", json.dumps(USERS))
    monkeypatch.setenv("DEMO_RESET_ENABLED", "false")
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://evaluator.example")
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    reset()
    with TestClient(main.app) as instance:
        yield instance
    reset()


@pytest.mark.parametrize("path", [
    "/api/aircraft", "/api/health", "/api/inventory", "/api/audit",
    "/api/demo/scenario", "/docs", "/openapi.json", "/redoc", "/login",
])
def test_reads_and_documentation_require_authentication(client, path):
    response = client.get(path, headers={"X-Demo-Role": "commander"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic ")


def test_every_registered_mutation_is_gated_before_routing(client):
    before = snapshot()
    for route in main.app.routes:
        for method in getattr(route, "methods", set()) & {"POST", "PUT", "PATCH", "DELETE"}:
            # Even invalid bodies and unresolved path parameters must be gated.
            response = client.request(method, route.path, headers={"X-Demo-Role": "commander"})
            assert response.status_code == 401, (method, route.path, response.text)
    assert snapshot() == before


@pytest.mark.parametrize("authorization", ["", "Basic ???", "Basic Og==", "Bearer bogus", "Basic /w=="])
def test_invalid_authentication_is_safe(client, authorization):
    response = client.get("/api/aircraft", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
    assert PASSWORD not in response.text


@pytest.mark.parametrize("auth", [("leader", "wrong"), ("unknown", PASSWORD)])
def test_wrong_password_or_unknown_user_is_rejected(client, auth):
    assert client.get("/api/aircraft", auth=auth).status_code == 401


def test_headers_and_body_cannot_elevate_authenticated_role(client):
    before = snapshot()
    response = client.post("/api/recommendations/A17/reject", auth=("supply", PASSWORD),
                           headers={"X-Demo-Role": "commander"}, json={"actor": "commander"})
    assert response.status_code == 403
    assert snapshot() == before
    allowed = client.patch("/api/inventory/inv-04", auth=("supply", PASSWORD),
                           headers={"X-Demo-Role": "commander"}, json={"quantity": 5})
    assert allowed.status_code == 200


def test_base_is_bound_to_account_even_with_duplicate_claim_headers(client):
    before = snapshot()
    response = client.post("/api/maintenance/work-orders?aircraft_id=A17", auth=("alpha", PASSWORD),
                           headers=[("X-Demo-Role", "commander"), ("X-Demo-Role", "logistics"),
                                    ("X-Demo-Base", "bravo")], json={"component": "HP-204"})
    assert response.status_code == 200
    response = client.post("/api/maintenance/work-orders?aircraft_id=A24", auth=("alpha", PASSWORD),
                           headers={"X-Demo-Base": "bravo"}, json={"component": "HP-204"})
    # A24 belongs to bravo; a caller cannot select it by spoofing the base.
    assert response.status_code == 403
    assert snapshot() != before


def test_reset_requires_explicit_enable_and_commander(client, monkeypatch):
    before = snapshot()
    assert client.post("/api/demo/reset", auth=("leader", PASSWORD)).status_code == 403
    assert snapshot() == before
    monkeypatch.setenv("DEMO_RESET_ENABLED", "true")
    assert client.post("/api/demo/reset", auth=("supply", PASSWORD),
                       headers={"X-Demo-Role": "commander"}).status_code == 403
    assert client.post("/api/demo/reset", auth=("leader", PASSWORD)).status_code == 200


def test_explicit_local_reset_retains_existing_workflow(client, monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_MODE", "local")
    monkeypatch.setenv("DEMO_RESET_ENABLED", "true")
    assert client.post("/api/demo/reset", headers={"X-Demo-Role": "logistics"}).status_code == 403
    assert client.post("/api/demo/reset", headers={"X-Demo-Role": "commander"}).status_code == 200


def test_missing_configuration_locks_api_but_keeps_liveness(client, monkeypatch):
    monkeypatch.delenv("DEMO_BASIC_USERS")
    assert client.get("/api/health").status_code == 503
    assert client.get("/livez").json() == {"ok": True}
    monkeypatch.delenv("DEMO_ACCESS_MODE")
    assert access_mode() == "restricted"
    assert client.get("/api/aircraft").status_code == 503


@pytest.mark.parametrize("value", ['{"secret":', '[]', '{"user":{"role":"commander","password":"short"}}',
                                   '{"user":{"role":"base","password":"long-enough-test-password","base":"unknown"}}'])
def test_bad_account_config_fails_without_echoing_secret(client, monkeypatch, value):
    monkeypatch.setenv("DEMO_BASIC_USERS", value)
    with pytest.raises(RuntimeError, match="^Invalid DEMO_BASIC_USERS configuration$"):
        validate_access_config()


def test_restricted_config_rejects_compat_and_wildcard(client, monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "compat")
    with pytest.raises(RuntimeError, match="hardened"):
        validate_access_config()
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "hardened")
    monkeypatch.setenv("FRONTEND_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="explicit trusted origins"):
        validate_access_config()


def test_cors_only_allows_configured_origins(client):
    # Same production CORS configuration, wrapped around the actual API.
    cors_app = CORSMiddleware(main.app, allow_origins=frontend_origins(),
                             allow_methods=["*"], allow_headers=["*"])
    with TestClient(cors_app) as browser:
        headers = {"Origin": "https://evaluator.example", "Access-Control-Request-Method": "POST",
                   "Access-Control-Request-Headers": "authorization,x-demo-role"}
        trusted = browser.options("/api/demo/reset", headers=headers)
        assert trusted.status_code == 200
        assert trusted.headers["access-control-allow-origin"] == headers["Origin"]
        headers["Origin"] = "https://untrusted.example"
        rejected = browser.options("/api/demo/reset", headers=headers)
        assert rejected.status_code == 400
        assert "access-control-allow-origin" not in rejected.headers
        read = browser.get("/api/aircraft", auth=("leader", PASSWORD),
                           headers={"Origin": "https://untrusted.example"})
        assert "access-control-allow-origin" not in read.headers


def test_browser_mutations_reject_untrusted_origin(client):
    before = snapshot()
    for headers in ({"Origin": "https://untrusted.example"}, {"Origin": "null"},
                    {"Sec-Fetch-Site": "cross-site"}):
        response = client.patch("/api/inventory/inv-04", auth=("supply", PASSWORD),
                                headers=headers, json={"quantity": 5})
        assert response.status_code == 403
    assert snapshot() == before
    assert client.patch("/api/inventory/inv-04", auth=("supply", PASSWORD),
                        headers={"Origin": "https://evaluator.example"}, json={"quantity": 5}).status_code == 200


def test_browser_login_challenge_and_redirect(client):
    response = client.get("/login", auth=("leader", PASSWORD), follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert response.headers["cache-control"] == "no-store"


def test_authorized_closed_loop_uses_authenticated_accounts(client):
    prediction = client.post("/api/aircraft/A17/predict", auth=("alpha", PASSWORD))
    assert prediction.status_code == 200
    recommendation = client.get("/api/work-orders/WO-1042/recommendation", auth=("leader", PASSWORD))
    assert recommendation.status_code == 200
    approved = client.post("/api/work-orders/WO-1042/recommendation/approve", auth=("leader", PASSWORD), json={})
    assert approved.status_code == 200, approved.text
    transfer_id = approved.json()["transfer"]["id"]
    received = client.post(f"/api/transfers/{transfer_id}/receive", auth=("supply", PASSWORD))
    assert received.status_code == 200, received.text
    for action in ("start", "complete"):
        response = client.post(f"/api/maintenance/work-orders/WO-1042/{action}", auth=("alpha", PASSWORD))
        assert response.status_code == 200, response.text
    assert response.json()["status"] == "COMPLETED"
    assert client.get("/api/fleet/overview", auth=("leader", PASSWORD)).status_code == 200
