"""Parts and inventory persistence.

Inventory rows carry the three quantities the fleet-aware allocation logic
needs (spec section 9):

    quantity           total units physically held
    reserved           units committed to another work order
    minimum_reserve    units this base keeps for itself

    available_for_transfer = quantity - reserved - minimum_reserve
"""

from __future__ import annotations

from .store import lock, next_id, store

DEFAULT_MIN_CONDITION_PCT = 40


class PartRepository:
    @staticmethod
    def list_all() -> list[dict]:
        return list(store()["parts"])

    @staticmethod
    def get(part_number: str) -> dict | None:
        key = str(part_number).upper()
        return next((p for p in store()["parts"] if str(p["part_number"]).upper() == key), None)

    @staticmethod
    def min_condition_pct(part_number: str) -> int:
        part = PartRepository.get(part_number)
        return int(part.get("min_condition_pct", DEFAULT_MIN_CONDITION_PCT)) if part else DEFAULT_MIN_CONDITION_PCT

    @staticmethod
    def name(part_number: str) -> str:
        part = PartRepository.get(part_number)
        return part.get("name") if part else str(part_number)


def available_for_transfer(inv: dict) -> int:
    """Units at a base that may legitimately be moved elsewhere."""
    return (
        int(inv.get("quantity", 0))
        - int(inv.get("reserved", 0))
        - int(inv.get("minimum_reserve", 0))
    )


class InventoryRepository:
    @staticmethod
    def list_all() -> list[dict]:
        return list(store()["inventory"])

    @staticmethod
    def get(inv_id: str) -> dict | None:
        return next((i for i in store()["inventory"] if i["id"] == inv_id), None)

    @staticmethod
    def find(base_id: str, part_number: str) -> dict | None:
        key = str(part_number).upper()
        return next(
            (i for i in store()["inventory"]
             if i["base_id"] == base_id and str(i["part_number"]).upper() == key),
            None,
        )

    @staticmethod
    def find_all_for_part(part_number: str) -> list[dict]:
        key = str(part_number).upper()
        return [i for i in store()["inventory"] if str(i["part_number"]).upper() == key]

    @staticmethod
    def update(inv_id: str, **fields) -> dict | None:
        inv = InventoryRepository.get(inv_id)
        if inv is None:
            return None
        with lock():
            inv.update(fields)
        return inv

    @staticmethod
    def ensure_line(base_id: str, part_number: str) -> dict:
        """Get or create the stock line for a (base, part) pair."""
        inv = InventoryRepository.find(base_id, part_number)
        if inv:
            return inv
        inv = {
            "id": next_id("inventory_seq", "inv-", 2),
            "base_id": base_id,
            "part_number": str(part_number).upper(),
            "quantity": 0,
            "reserved": 0,
            "minimum_reserve": 0,
            "condition_pct": 0,
            "status": "STOCKOUT",
        }
        with lock():
            store()["inventory"].append(inv)
        return inv

    @staticmethod
    def set_quantity(inv_id: str, quantity: int, condition_pct: int | None = None) -> dict | None:
        """Set an absolute quantity and keep derived status consistent."""
        inv = InventoryRepository.get(inv_id)
        if inv is None:
            return None
        fields: dict = {"quantity": quantity}
        if condition_pct is not None:
            fields["condition_pct"] = condition_pct
        inv = InventoryRepository.update(inv_id, **fields)
        return refresh_line_status(inv)


def refresh_line_status(inv: dict) -> dict:
    """Derive the stock status from quantities rather than trusting a field."""
    if int(inv.get("quantity", 0)) <= 0:
        inv["status"] = "STOCKOUT"
    elif available_for_transfer(inv) <= 0:
        inv["status"] = "LOW_STOCK"
    else:
        inv["status"] = "AVAILABLE"
    return inv