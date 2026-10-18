"""Repositories — the persistence boundary.

Services depend on these, never on the raw in-memory dict. Replacing this
package with PostgreSQL + SQLAlchemy is the only change needed to make the
application persistent.
"""

from .store import lock, next_id, reset, snapshot, store
from .aircraft_repository import AircraftRepository
from .inventory_repository import (
    InventoryRepository,
    PartRepository,
    available_for_transfer,
    refresh_line_status,
)
from .maintenance_repository import (
    EventRepository,
    WorkOrderRepository,
    OPEN_WORK_ORDER_STATUSES,
    UNRESOLVED_EVENT_STATUSES,
)
from .transfer_repository import TransferRepository, ACTIVE_TRANSFER_STATUSES
from .audit_repository import AuditRepository, PredictionHistoryRepository

__all__ = [
    "store", "lock", "next_id", "reset", "snapshot",
    "AircraftRepository",
    "InventoryRepository", "PartRepository", "available_for_transfer", "refresh_line_status",
    "EventRepository", "WorkOrderRepository",
    "OPEN_WORK_ORDER_STATUSES", "UNRESOLVED_EVENT_STATUSES",
    "TransferRepository", "ACTIVE_TRANSFER_STATUSES",
    "AuditRepository", "PredictionHistoryRepository",
]