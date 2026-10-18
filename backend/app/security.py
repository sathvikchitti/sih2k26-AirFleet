"""Demo-mode authorization checks.

Actors are caller-selected role labels in this POC; checks enforce the
capability matrix for ordinary demo requests but do not authenticate identity.
"""

import os

from fastapi import HTTPException

from .domain.enums import Permission, Role, role_has


def permission_mode() -> str:
    """Return the configured demo authorization mode, failing closed on typos."""
    mode = os.getenv("DEMO_PERMISSION_MODE", "hardened").strip().lower()
    if mode not in {"hardened", "compat"}:
        raise RuntimeError("DEMO_PERMISSION_MODE must be 'hardened' or 'compat'")
    return mode


def validate_permission_config() -> None:
    permission_mode()


def reset_enabled() -> bool:
    return os.getenv("DEMO_RESET_ENABLED", "false").strip().lower() in {"1", "true", "yes"}


def _known_base(base: str) -> bool:
    from .data import BASES
    return base.strip().lower() in {str(row["id"]).lower() for row in BASES}


def require_demo_permission(actor: str, *permissions: Permission,
                            demo_role: str | None = None,
                            demo_base: str | None = None,
                            resource_base: str | None = None) -> str:
    mode = permission_mode()
    # Demo headers select caller-claimed roles; they are not authenticated
    # principals. Hardened mode requires explicit selection. Compat retains
    # actor fallback for older clients, while a present header always wins.
    if mode == "hardened" and not demo_role:
        raise HTTPException(status_code=403, detail="X-Demo-Role is required")
    role = str(demo_role if demo_role is not None else actor or "").strip().lower()
    if role not in {item.value for item in Role}:
        raise HTTPException(status_code=403, detail="unknown demo role")
    if demo_base is not None and not _known_base(demo_base):
        raise HTTPException(status_code=403, detail="unknown X-Demo-Base")
    if not any(role_has(role, permission) for permission in permissions):
        raise HTTPException(status_code=403, detail="demo role is not permitted to perform this action")
    # Keep base scope whenever either claim header is used, including compat
    # mode. Only calls with no demo headers retain the unscoped legacy fallback.
    if role == Role.BASE_MANAGER.value and (demo_role is not None or demo_base is not None):
        if not demo_base:
            raise HTTPException(status_code=403, detail="Base Manager requests require X-Demo-Base")
        if resource_base and demo_base.strip().lower() != resource_base.strip().lower():
            raise HTTPException(status_code=403, detail="resource is outside the selected demo base")
    return role
