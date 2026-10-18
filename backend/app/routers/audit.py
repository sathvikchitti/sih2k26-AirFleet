"""Audit trail endpoints (spec section 18)."""

from __future__ import annotations

from fastapi import APIRouter

from ..domain.enums import ROLE_PERMISSIONS, Role
from ..services import audit_service

router = APIRouter(tags=["audit"])


@router.get("/api/audit")
def audit_log(entity_id: str | None = None, event_type: str | None = None,
              entity_type: str | None = None, limit: int | None = None):
    """Chronological event log. Generic — not tied to any screen."""
    rows = audit_service.timeline(entity_id=entity_id, limit=limit)
    if event_type:
        rows = [r for r in rows if r["event_type"] == event_type]
    if entity_type:
        rows = [r for r in rows if r["entity_type"] == entity_type]
    return {"events": rows, "count": len(rows)}


@router.get("/api/audit/permissions")
def permissions():
    """Role capability matrix (spec section 19).

    Declared centrally so the UI and the API agree on what a role may do.
    """
    return {
        role.value: sorted(p.value for p in perms)
        for role, perms in ROLE_PERMISSIONS.items()
    }