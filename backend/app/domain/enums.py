"""Domain vocabulary.

Single source of truth for every state machine in the system. Both the
services and the legacy compatibility layer import from here so that status
vocabulary can never drift between the new model and the old endpoints.
"""

from __future__ import annotations

from enum import StrEnum


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Ordered by operational severity — ranking helpers rely on this order.
RISK_ORDER = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 2, RiskLevel.HIGH: 3, RiskLevel.CRITICAL: 4}


class AircraftStatus(StrEnum):
    """Operational state of an airframe.

    Availability is derived from this: only AVAILABLE counts toward the
    north-star metric (spec section 13).
    """

    AVAILABLE = "AVAILABLE"
    AT_RISK = "AT_RISK"
    DEGRADED = "DEGRADED"
    WAITING_FOR_PART = "WAITING_FOR_PART"
    MAINTENANCE = "MAINTENANCE"
    UNAVAILABLE = "UNAVAILABLE"


# The only state that counts as "flyable".
FLYABLE_STATUSES = frozenset({AircraftStatus.AVAILABLE})


class WorkOrderStatus(StrEnum):
    """Lifecycle of a maintenance work order (spec section 5)."""

    OPEN = "OPEN"
    WAITING_FOR_RESOURCE = "WAITING_FOR_RESOURCE"
    RESOURCE_AVAILABLE = "RESOURCE_AVAILABLE"
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


OPEN_WORK_ORDER_STATUSES = frozenset({
    WorkOrderStatus.OPEN,
    WorkOrderStatus.WAITING_FOR_RESOURCE,
    WorkOrderStatus.RESOURCE_AVAILABLE,
    WorkOrderStatus.SCHEDULED,
    WorkOrderStatus.IN_PROGRESS,
})

# Statuses that mean the aircraft is not flyable because of this work order.
GROUNDING_WORK_ORDER_STATUSES = frozenset({
    WorkOrderStatus.WAITING_FOR_RESOURCE,
    WorkOrderStatus.IN_PROGRESS,
})


class MaintenanceEventStatus(StrEnum):
    """Lifecycle of a predicted maintenance event (spec section 3).

    A prediction is NOT a work order: an event must be triaged before work
    begins.
    """

    OPEN = "OPEN"
    TRIAGED = "TRIAGED"
    WORK_ORDER_CREATED = "WORK_ORDER_CREATED"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class TransferStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class MaintenanceSource(StrEnum):
    PREDICTED_MAINTENANCE = "PREDICTED_MAINTENANCE"
    MANUAL = "MANUAL"
    INSPECTION = "INSPECTION"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


PRIORITY_ORDER = {Priority.LOW: 1, Priority.MEDIUM: 2, Priority.HIGH: 3, Priority.CRITICAL: 4}


class InventoryStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    LOW_STOCK = "LOW_STOCK"
    STOCKOUT = "STOCKOUT"


class AuditEventType(StrEnum):
    PREDICTION_GENERATED = "PREDICTION_GENERATED"
    MAINTENANCE_EVENT_CREATED = "MAINTENANCE_EVENT_CREATED"
    MAINTENANCE_EVENT_DISMISSED = "MAINTENANCE_EVENT_DISMISSED"
    WORK_ORDER_CREATED = "WORK_ORDER_CREATED"
    WORK_ORDER_STATUS_CHANGED = "WORK_ORDER_STATUS_CHANGED"
    RECOMMENDATION_GENERATED = "RECOMMENDATION_GENERATED"
    RECOMMENDATION_APPROVED = "RECOMMENDATION_APPROVED"
    RECOMMENDATION_REJECTED = "RECOMMENDATION_REJECTED"
    INVENTORY_UPDATED = "INVENTORY_UPDATED"
    TRANSFER_CREATED = "TRANSFER_CREATED"
    TRANSFER_STARTED = "TRANSFER_STARTED"
    TRANSFER_RECEIVED = "TRANSFER_RECEIVED"
    MAINTENANCE_STARTED = "MAINTENANCE_STARTED"
    MAINTENANCE_COMPLETED = "MAINTENANCE_COMPLETED"
    AIRCRAFT_RETURNED_TO_SERVICE = "AIRCRAFT_RETURNED_TO_SERVICE"
    RESERVE_OVERRIDE_APPLIED = "RESERVE_OVERRIDE_APPLIED"
    DEMO_RESET = "DEMO_RESET"


class Role(StrEnum):
    COMMANDER = "commander"
    BASE_MANAGER = "base"
    LOGISTICS = "logistics"


# Permission matrix (spec section 19). The POC still uses demo role selection,
# but authorisation is now explicit rather than implied by which screen you
# happen to be on.
class Permission(StrEnum):
    VIEW_FLEET = "fleet:view"
    VIEW_ALL_BASES = "bases:view_all"
    VIEW_RECOMMENDATIONS = "recommendations:view"
    APPROVE_RECOMMENDATION = "recommendations:approve"
    VIEW_FLEET_IMPACT = "impact:view"
    VIEW_OWN_BASE = "base:view_own"
    REQUEST_RESOURCE = "resource:request"
    MANAGE_INVENTORY = "inventory:manage"
    MANAGE_TRANSFERS = "transfers:manage"
    MANAGE_RESERVATIONS = "reservations:manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.COMMANDER: frozenset({
        Permission.VIEW_FLEET,
        Permission.VIEW_ALL_BASES,
        Permission.VIEW_RECOMMENDATIONS,
        Permission.APPROVE_RECOMMENDATION,
        Permission.VIEW_FLEET_IMPACT,
    }),
    Role.BASE_MANAGER: frozenset({
        Permission.VIEW_OWN_BASE,
        Permission.REQUEST_RESOURCE,
    }),
    Role.LOGISTICS: frozenset({
        Permission.MANAGE_INVENTORY,
        Permission.MANAGE_TRANSFERS,
        Permission.MANAGE_RESERVATIONS,
    }),
}


def role_has(role: str, permission: Permission) -> bool:
    try:
        return permission in ROLE_PERMISSIONS[Role(role)]
    except (KeyError, ValueError):
        return False
