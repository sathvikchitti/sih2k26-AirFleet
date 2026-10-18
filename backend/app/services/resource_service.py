"""Resource service: cross-base search for a work order's requirement.

Answers "where could this part come from?" across every base, and separates

  * infeasible candidates (with the reason), and
  * feasible candidates (rankable by the recommendation engine)

Feasibility is a hard constraint set, deliberately separate from scoring: no
amount of urgency should ever make an unserviceable part look attractive.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..data import BASES, distance_km, eta_hours
from ..domain import knowledge
from ..domain.enums import Priority, WorkOrderStatus
from ..repositories import (
    AircraftRepository,
    InventoryRepository,
    PartRepository,
    WorkOrderRepository,
    available_for_transfer,
)
from ..repositories.inventory_repository import DEFAULT_MIN_CONDITION_PCT
from .ml import get_provider, predict_validated

# Why a candidate was rejected. Surfaced verbatim in recommendations so the
# decision is explainable (spec sections 5 and 11).
INFEASIBLE_NO_STOCK = "NO_STOCK"
INFEASIBLE_CONDITION = "CONDITION_BELOW_MINIMUM"
INFEASIBLE_RESERVE = "MINIMUM_RESERVE_VIOLATION"
INFEASIBLE_UNKNOWN_PART = "PART_NOT_IN_CATALOGUE"
INFEASIBLE_SAME_BASE = "SAME_BASE"


@dataclass(frozen=True)
class ResourceContext:
    """Immutable catalog and route inputs for an isolated planning scenario.

    Normal application calls omit this and retain the repository-backed demo
    catalog. Evaluation scenarios provide values here rather than mutating
    module globals or repositories.
    """

    bases: tuple[tuple[str, str], ...]
    parts: tuple[tuple[str, str, int], ...]
    routes: tuple[tuple[str, str, float, float], ...]

    def base_rows(self) -> list[dict]:
        return [{"id": base_id, "name": name} for base_id, name in self.bases]

    def part(self, part_number: str) -> tuple[str, int] | None:
        target = str(part_number).upper()
        return next(((name, condition) for pn, name, condition in self.parts if pn == target), None)

    def route(self, origin: str, destination: str) -> tuple[float, float]:
        origin, destination = origin.lower(), destination.lower()
        if origin == destination:
            return 0.0, 0.0
        for left, right, distance, eta in self.routes:
            if (left == origin and right == destination) or (left == destination and right == origin):
                return float(distance), float(eta)
        raise ValueError(f"resource context has no route between {origin} and {destination}")

    def part_min_condition(self, part_number: str) -> int | None:
        part = self.part(part_number)
        return part[1] if part else None

    def part_name(self, part_number: str) -> str | None:
        part = self.part(part_number)
        return part[0] if part else None


def part_min_condition(part_number: str) -> int:
    return PartRepository.min_condition_pct(part_number)


def search(work_order_id: str) -> dict:
    """Find every feasible and infeasible source for a work order's part."""
    work_order = WorkOrderRepository.get(work_order_id)
    if work_order is None:
        return {"work_order_id": work_order_id, "error": "unknown work order", "candidates": []}

    return search_from_snapshot(work_order, InventoryRepository.list_all())


def search_from_snapshot(work_order: dict, inventory_rows: list[dict], *,
                         resource_context: ResourceContext | None = None) -> dict:
    """Run the canonical hard-constraint search against supplied inventory.

    `inventory_rows` is read-only input. Callers can pass a cloned/virtual
    ledger for previews without editing repositories or weakening the live
    approval checks.
    """
    work_order_id = str(work_order.get("id") or work_order.get("work_order_id") or "")
    inventory = {(str(row.get("base_id", "")).lower(),
                  str(row.get("part_number", "")).upper()): row
                 for row in inventory_rows}

    component = work_order.get("required_component")
    if not component:
        return {
            "work_order_id": work_order_id,
            "aircraft_id": work_order["aircraft_id"],
            "required_component": None,
            "min_condition_pct": None,
            "candidates": [],
            "infeasible": [],
        }

    context_part = resource_context.part(component) if resource_context else None
    if (context_part is None if resource_context else PartRepository.get(component) is None):
        bases = resource_context.base_rows() if resource_context else BASES
        return {
            "work_order_id": work_order_id,
            "aircraft_id": work_order["aircraft_id"],
            "required_component": component,
            "min_condition_pct": None,
            "candidates": [],
            "infeasible": [{
                "base_id": b["id"], "part_number": component, "feasible": False,
                "reason": INFEASIBLE_UNKNOWN_PART,
                "detail": f"{component} is not in the parts catalogue",
            } for b in bases],
        }

    home = work_order["base_id"]
    min_cond = (resource_context.part_min_condition(component) if resource_context
                else part_min_condition(component))
    bases = resource_context.base_rows() if resource_context else BASES

    candidates: list[dict] = []
    infeasible: list[dict] = []

    for base in bases:
        if base["id"] == home:
            # Local stock is handled separately: no transfer required.
            continue

        inv = inventory.get((base["id"].lower(), str(component).upper()))
        quantity = int(inv.get("quantity", 0)) if inv else 0
        reserved = int(inv.get("reserved", 0)) if inv else 0
        minimum_reserve = int(inv.get("minimum_reserve", 0)) if inv else 0
        condition = int(inv.get("condition_pct", 0)) if inv else 0
        transferable = max(0, quantity - reserved - minimum_reserve)
        distance, eta = (resource_context.route(home, base["id"]) if resource_context
                         else (distance_km(home, base["id"]), eta_hours(home, base["id"])))
        part_name = resource_context.part_name(component) if resource_context else PartRepository.name(component)

        candidate = {
            "base_id": base["id"],
            "base_name": base["name"],
            "part_number": component,
            "part_name": part_name,
            "quantity_available": transferable,
            "quantity_total": quantity,
            "reserved_quantity": reserved,
            "minimum_reserve": minimum_reserve,
            "condition_pct": condition,
            "min_condition_pct": min_cond,
            "distance_km": distance,
            "eta_hours": eta,
            "donor_reserve_after_transfer": quantity - 1 if transferable > 0 else quantity,
        }

        if quantity <= 0:
            candidate.update(feasible=False, reason=INFEASIBLE_NO_STOCK,
                             detail=f"{base['name']} holds no {component}")
        elif transferable <= 0:
            candidate.update(
                feasible=False, reason=INFEASIBLE_RESERVE,
                detail=(
                    f"{base['name']} holds {quantity} but {reserved} reserved + "
                    f"{minimum_reserve} minimum reserve leaves nothing transferable"
                ),
            )
        elif condition < min_cond:
            candidate.update(
                feasible=False, reason=INFEASIBLE_CONDITION,
                detail=f"Condition {condition}% is below the {min_cond}% minimum for {component}",
            )
        else:
            candidate.update(feasible=True, reason=None, detail=None)

        (candidates if candidate["feasible"] else infeasible).append(candidate)

    # Local availability is not a "candidate" but must be visible.
    local = inventory.get((str(home).lower(), str(component).upper()))
    local_available = max(0, available_for_transfer(local)) if local else 0
    if local and int(local.get("condition_pct", 0)) < min_cond:
        local_available = 0

    return {
        "work_order_id": work_order_id,
        "aircraft_id": work_order["aircraft_id"],
        "home_base": home,
        "required_component": component,
        "part_name": resource_context.part_name(component) if resource_context else PartRepository.name(component),
        "min_condition_pct": min_cond,
        "local_available": local_available,
        "local_condition_pct": int(local.get("condition_pct", 0)) if local else 0,
        "candidates": candidates,
        "infeasible": infeasible,
        "bases_searched": [b["id"] for b in bases],
    }


def local_availability(work_order: dict) -> dict:
    """Is the required part already usable at the aircraft's own base?"""
    component = work_order.get("required_component")
    if not component:
        return {"component": None, "available": False}
    inv = InventoryRepository.find(work_order["base_id"], component)
    if not inv:
        return {"component": component, "available": False, "quantity": 0}
    free = int(inv.get("quantity", 0)) - int(inv.get("reserved", 0))
    transferable = max(0, available_for_transfer(inv))
    condition = int(inv.get("condition_pct", 0))
    min_cond = part_min_condition(component)
    return {
        "component": component,
        "available": transferable > 0 and condition >= min_cond,
        "quantity": int(inv.get("quantity", 0)),
        "free": free,
        "available_for_transfer": transferable,
        "minimum_reserve": int(inv.get("minimum_reserve", 0)),
        "condition_pct": condition,
        "min_condition_pct": min_cond,
        "in_store": inv["id"],
    }


def urgency_weight(work_order: dict, risk_level: str | None = None, rul: float | None = None) -> float:
    """Composite urgency used to scale transport cost in scoring.

    Combines the three signals the spec lists: aircraft risk, work-order
    priority, and how soon the part is needed relative to remaining life.
    """
    weight = {
        Priority.CRITICAL.value: 4.0,
        Priority.HIGH.value: 3.0,
        Priority.MEDIUM.value: 2.0,
        Priority.LOW.value: 1.0,
    }.get(work_order.get("priority"), 2.0)

    if risk_level in ("CRITICAL",):
        weight += 1.0
    elif risk_level == "HIGH":
        weight += 0.5

    # These operational cutoffs are defined in flight hours. Do not apply
    # them to C-MAPSS cycle counts without a justified conversion.
    if work_order.get("rul_unit", "flight_hours") in (None, "flight_hours"):
        if rul is not None and rul <= 15:
            weight += 2.0
        elif rul is not None and rul <= 40:
            weight += 1.0

    return weight


# --------------------------------------------------------------------------
# Demand vs supply
# --------------------------------------------------------------------------
def demand_summary(scope_base: str | None = None) -> dict:
    """Fleet-wide (or single-base) demand-versus-supply picture.

    The UI renders this rather than recomputing shortfalls itself — the
    availability arithmetic belongs to the service layer (spec section 22).
    """
    aircraft = (AircraftRepository.list_by_base(scope_base)
                if scope_base else AircraftRepository.list_all())
    visible_bases = [b for b in BASES if (scope_base is None or b["id"] == scope_base)]
    scope_ids = {a["id"] for a in aircraft}

    # Which component each airframe needs comes from the ML provider plus the
    # knowledge layer. Aircraft rows do not store this, so resolve it here.
    provider = get_provider()
    required_by: dict[str, str] = {}
    predictions = {}
    for a in aircraft:
        pred = predict_validated(provider, a["id"])
        predictions[a["id"]] = pred
        res = knowledge.resolve(pred.get("subsystem"), pred.get("predicted_issue"))
        if res.matched and res.candidate_components:
            required_by[a["id"]] = res.candidate_components[0]

    rows = []
    for part in PartRepository.list_all():
        pn = part["part_number"]
        min_cond = int(part.get("min_condition_pct", DEFAULT_MIN_CONDITION_PCT))

        # Demand = aircraft the ML service flags as needing this component.
        needing = [
            {
                "id": a["id"],
                "base_id": a["base_id"],
                "status": a.get("status"),
                "risk_level": predictions[a["id"]].get("risk_level"),
                "rul": predictions[a["id"]].get("rul"),
                "rul_unit": predictions[a["id"]].get("rul_unit"),
                "required_component": pn,
            }
            for a in aircraft
            if required_by.get(a["id"]) == pn
        ]

        lines = []
        for base in visible_bases:
            inv = InventoryRepository.find(base["id"], pn)
            quantity = int(inv.get("quantity", 0)) if inv else 0
            reserved = int(inv.get("reserved", 0)) if inv else 0
            minimum = int(inv.get("minimum_reserve", 0)) if inv else 0
            condition = int(inv.get("condition_pct", 0)) if inv else 0
            transferable = max(0, quantity - reserved - minimum)
            lines.append({
                "base_id": base["id"],
                "base_name": base["name"],
                "quantity": quantity,
                "reserved": reserved,
                "minimum_reserve": minimum,
                "available_for_transfer": transferable,
                "condition_pct": condition if quantity > 0 else None,
                "min_condition_pct": min_cond,
                "serviceable": quantity > 0 and condition >= min_cond,
                "status": inv["status"] if inv else "NOT_STOCKED",
            })

        total_free = sum(l["available_for_transfer"] for l in lines)
        total_qty = sum(l["quantity"] for l in lines)
        demand = len(needing)
        # Open work orders for this part add to demand beyond current flags.
        open_wos = [
            w for w in WorkOrderRepository.find_by_component(pn)
            if w["aircraft_id"] in scope_ids and w["status"] != WorkOrderStatus.COMPLETED.value
        ]

        rows.append({
            "part_number": pn,
            "name": part["name"],
            "category": part["category"],
            "min_condition_pct": min_cond,
            "lines": lines,
            "demand": demand,
            "needing": needing,
            "open_work_orders": [
                {"id": w["id"], "aircraft_id": w["aircraft_id"], "status": w["status"]}
                for w in open_wos
            ],
            "total_quantity": total_qty,
            "total_free": total_free,
            "serviceable_bases": [l["base_id"] for l in lines if l["serviceable"]],
            "shortfall": max(0, demand - total_free),
        })

    in_demand = [r for r in rows if r["demand"] > 0 or r["open_work_orders"]]
    return {
        "scope_base": scope_base,
        "parts": rows,
        "in_demand": in_demand,
        "shortages": [r for r in in_demand if r["shortfall"] > 0
                      or not any(l["serviceable"] for l in r["lines"])],
        "totals": {
            "part_types": len(rows),
            "stock_lines": len(InventoryRepository.list_all()),
            "units_on_hand": sum(int(i.get("quantity", 0)) for i in InventoryRepository.list_all()),
            "units_reserved": sum(int(i.get("reserved", 0)) for i in InventoryRepository.list_all()),
            "units_free": sum(max(0, available_for_transfer(i)) for i in InventoryRepository.list_all()),
            "stockouts": sum(1 for i in InventoryRepository.list_all() if i["status"] == "STOCKOUT"),
            "unserviceable": sum(
                1 for i in InventoryRepository.list_all()
                if int(i.get("quantity", 0)) > 0
                and int(i.get("condition_pct", 0)) < PartRepository.min_condition_pct(i["part_number"])
            ),
        },
    }
