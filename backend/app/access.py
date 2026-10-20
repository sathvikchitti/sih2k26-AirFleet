"""Time-limited evaluator access using standard HTTP Basic authentication.

All routes are gated before routing; role/base claims are replaced with the
authenticated account's server-side assignments. Local mode is explicit.
"""

import json
import os
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic
from starlette.datastructures import MutableHeaders

from .security import _known_base, permission_mode

basic = HTTPBasic(realm="Air Fleet evaluator")


def access_mode():
    mode = os.getenv("DEMO_ACCESS_MODE", "restricted").strip().lower()
    if mode not in {"local", "restricted"}:
        raise RuntimeError("DEMO_ACCESS_MODE must be 'local' or 'restricted'")
    return mode


def frontend_origins():
    default = "http://localhost:5173,http://127.0.0.1:5173" if access_mode() == "local" else ""
    origins = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", default).split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError("FRONTEND_ORIGINS must list explicit trusted origins")
    return origins


def accounts():
    # Environment is server-only. Never include its value in diagnostics.
    try:
        rows = json.loads(os.getenv("DEMO_BASIC_USERS") or "{}")
        if not isinstance(rows, dict):
            raise ValueError
        for name, row in rows.items():
            if (not name or ":" in name or not name.isascii()
                    or not isinstance(row, dict)
                    or row.get("role") not in {"commander", "base", "logistics"}
                    or not isinstance(row.get("password"), str)
                    or len(row["password"]) < 20 or not row["password"].isascii()
                    or (row["role"] == "base" and not _known_base(str(row.get("base", ""))))):
                raise ValueError
        return rows
    except (ValueError, TypeError, AttributeError):
        raise RuntimeError("Invalid DEMO_BASIC_USERS configuration") from None


def validate_access_config():
    frontend_origins()
    if access_mode() == "restricted":
        if permission_mode() != "hardened":
            raise RuntimeError("Restricted access requires DEMO_PERMISSION_MODE=hardened")
        accounts()  # Empty configuration locks all application routes.


async def evaluator_access(request: Request, call_next):
    if access_mode() == "local":
        return await call_next(request)
    # Minimal liveness response only; /api/health contains fleet predictions.
    if request.url.path == "/livez" and request.method in {"GET", "HEAD"}:
        return JSONResponse({"ok": True})
    # CORS handles preflights without revealing application data.
    if request.method == "OPTIONS" and "access-control-request-method" in request.headers:
        return await call_next(request)
    rows = accounts()
    if not rows:
        return JSONResponse({"detail": "evaluator access is not configured"}, status_code=503)
    try:
        credentials = await basic(request)
        account = rows.get(credentials.username)
        expected = account["password"] if account else "invalid-account-password"
        valid = secrets.compare_digest(credentials.password.encode(), expected.encode())
        if not valid or account is None:
            raise HTTPException(401, "Invalid credentials")
    except HTTPException:
        return JSONResponse({"detail": "Authentication required"}, status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Air Fleet evaluator"'})
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if ((origin is not None and origin not in frontend_origins())
                or request.headers.get("sec-fetch-site") == "cross-site"):
            return JSONResponse({"detail": "Untrusted request origin"}, status_code=403)
    # Remove ALL copies of caller-supplied claims before injecting trusted ones.
    headers = MutableHeaders(scope=request.scope)
    for name in ("x-demo-role", "x-demo-base"):
        if name in headers:
            del headers[name]
    headers["x-demo-role"] = account["role"]
    if account["role"] == "base":
        headers["x-demo-base"] = account["base"].strip().lower()
    # Request.headers may have been cached while authenticating.
    if hasattr(request, "_headers"):
        del request._headers
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response
