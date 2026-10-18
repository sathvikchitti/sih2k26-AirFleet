"""Application services — all business logic lives here.

No business logic belongs in routers or in the UI. Each service owns one
concern; `ml` is the only package that knows a model exists.
"""

from . import (
    audit_service,
    availability_service,
    compatibility,
    impact_service,
    maintenance_service,
    recommendation_service,
    resource_service,
    transfer_service,
)
from .ml import get_provider, set_provider

__all__ = [
    "audit_service",
    "availability_service",
    "compatibility",
    "impact_service",
    "maintenance_service",
    "recommendation_service",
    "resource_service",
    "transfer_service",
    "get_provider",
    "set_provider",
]