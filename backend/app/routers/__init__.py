"""API routers.

Split by domain per spec section 21. Every handler delegates to a service —
routers contain no business logic.
"""

from . import (
    aircraft,
    audit,
    bases,
    health,
    inventory,
    maintenance,
    recommendations,
    transfers,
)

__all__ = [
    "health", "aircraft", "bases", "inventory",
    "maintenance", "transfers", "recommendations", "audit",
]