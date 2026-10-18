"""End-to-end acceptance test for the documented demo scenario (spec sections 25 & 27).

Runs the full closed loop in-process:

    ML prediction -> predicted maintenance event -> work order
    -> cross-base search -> candidate ranking -> explainable recommendation
    -> human approval -> transfer -> received -> work order resourced
    -> maintenance started -> completed -> aircraft AVAILABLE
    -> fleet availability recalculated

Exits non-zero on the first failed assertion.

Run: python -m tests.test_workflow   (from backend/)
"""

from __future__ import annotations

import sys

sys.path.insert(0, ".")

from app.domain.enums import (
    AircraftStatus,
    MaintenanceEventStatus,
    TransferStatus,
    WorkOrderStatus,
)
from app.repositories import (
    EventRepository,
    InventoryRepository,
    TransferRepository,
    WorkOrderRepository,
    available_for_transfer,
    reset,
)
from app.services import (
    audit_service,
    availability_service,
    impact_service,
    maintenance_service,
    recommendation_service,
    resource_service,
    transfer_service,
)
from app.services.ml import get_provider

PASSED = 0
FAILED: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL  {label}{('  <- ' + detail) if detail else ''}")


def section(title: str) -> None:
    print(f"\n=== {title}")


def main() -> int:
    reset()
    availability_service.sync_aircraft_states()

    # ------------------------------------------------------------------
    section("1. ML prediction (no part numbers)")
    pred = get_provider().predict("A17")
    check("A17 health is 41", pred["health_score"] == 41, str(pred["health_score"]))
    check("A17 risk is CRITICAL from shared health/probability policy", pred["risk_level"] == "CRITICAL", pred["risk_level"])
    check("prediction includes traceable contract metadata",
          pred.get("model_version") == "mock-demo-v1"
          and pred.get("prediction_horizon_hours") == 72
          and pred.get("rul_unit") == "flight_hours")
    check("A17 RUL is 12h", pred["rul"] == 12, str(pred["rul"]))
    check(
        "prediction carries a subsystem, not a part",
        pred.get("subsystem") == "HIGH_PRESSURE" and not any(
            k in pred for k in ("required_component", "part_number", "part_id")
        ),
    )

    # ------------------------------------------------------------------
    section("2. Prediction -> predicted maintenance event (not a work order)")
    # The seed already represents prediction -> event -> work order for A17
    # (PM-001 + WO-1042). Ingesting a fresh prediction must create an event
    # and must NOT create a work order.
    fresh_event = maintenance_service.ingest_prediction("A17")
    check("a new prediction created a new event", fresh_event is not None and fresh_event["id"] != "PM-001")
    check("new event is OPEN", fresh_event["status"] == MaintenanceEventStatus.OPEN.value)
    check("event records the subsystem", fresh_event["subsystem"] == "HIGH_PRESSURE")
    check("event carries RUL 12", fresh_event["rul"] == 12)
    check("prediction did NOT auto-create a work order", fresh_event["work_order_id"] is None)
    check("no work order exists for the new event", WorkOrderRepository.find_by_event(fresh_event["id"]) is None)

    untriaged = [e for e in EventRepository.list_all() if e["status"] == MaintenanceEventStatus.OPEN.value]
    check("every untriaged event has no work order", all(e["work_order_id"] is None for e in untriaged))

    # ------------------------------------------------------------------
    section("3. Triage event -> work order (requires HP-204)")
    # A17's committed work order from the documented scenario.
    work_order = WorkOrderRepository.get("WO-1042")
    check("A17 work order exists", work_order is not None)
    check("work order is WO-1042", work_order["id"] == "WO-1042")
    check("requires HP-204 (from the knowledge layer)", work_order["required_component"] == "HP-204")
    check("source is predicted maintenance", work_order["source"] == "PREDICTED_MAINTENANCE")
    check("linked to its predicted event", work_order["predicted_event_id"] == "PM-001")
    check("status is WAITING_FOR_RESOURCE", work_order["status"] == WorkOrderStatus.WAITING_FOR_RESOURCE.value)
    check("predicted event marked WORK_ORDER_CREATED", EventRepository.get("PM-001")["status"] == MaintenanceEventStatus.WORK_ORDER_CREATED.value)

    # Prove the triage path end-to-end on an event nobody has actioned (PM-005,
    # A35 — high-pressure subsystem, deliberately left OPEN in the seed).
    a35_event = EventRepository.get("PM-005")
    a35_wo = maintenance_service.create_work_order_from_event("PM-005", actor="commander")
    check("untriaged event PM-005 can be triaged", a35_wo is not None and a35_wo["id"].startswith("WO-"))
    check("knowledge layer resolved HP-204 for A35", a35_wo["required_component"] == "HP-204")
    check("A35 work order links to PM-005", a35_wo["predicted_event_id"] == "PM-005")
    check("PM-005 now WORK_ORDER_CREATED", EventRepository.get("PM-005")["status"] == MaintenanceEventStatus.WORK_ORDER_CREATED.value)

    # An unknown subsystem must NOT be turned into a guessed work order.
    unknown = EventRepository.create(
        aircraft_id="A19", prediction_id="A19@x", predicted_issue="Unmodelled anomaly",
        subsystem="UNMAPPED", risk_level="HIGH", rul=10, confidence=0.5, health_score=50,
        predicted_time=None, required_resource_type="COMPONENT",
        status=MaintenanceEventStatus.OPEN.value, work_order_id=None,
        created_at="", updated_at="",
    )
    check(
        "unmapped subsystem cannot be auto-resourced",
        maintenance_service.create_work_order_from_event(unknown["id"]) is None,
    )

    # ------------------------------------------------------------------
    section("4. Cross-base resource search (all bases)")
    found = resource_service.search("WO-1042")
    check("home base is alpha", found["home_base"] == "alpha")
    check("required component is HP-204", found["required_component"] == "HP-204")
    check("all three bases searched", len(found["bases_searched"]) == 3)
    check("alpha has no stock (local_available 0)", found["local_available"] == 0)

    by_base = {c["base_id"]: c for c in found["candidates"] + found["infeasible"]}
    check("bravo present as feasible", by_base.get("bravo", {}).get("feasible") is True, str(by_base.get("bravo", {}).get("reason")))
    check("charlie present as feasible", by_base.get("charlie", {}).get("feasible") is True, str(by_base.get("charlie", {}).get("reason")))
    bravo = by_base["bravo"]
    check("bravo quantity_available is 1", bravo["quantity_available"] == 1, str(bravo["quantity_available"]))
    check("bravo condition is 42%", bravo["condition_pct"] == 42)
    check("bravo distance is 120km", bravo["distance_km"] == 120)
    check("charlie quantity_available is 2", by_base["charlie"]["quantity_available"] == 2)

    # ------------------------------------------------------------------
    section("5. Minimum reserve respected (fleet-aware, not inventory-aware)")
    charlie_oe = InventoryRepository.find("charlie", "OE-310")  # qty 3, reserved 0, min 1
    check(
        "charlie OE-310 transferable = qty - reserved - minimum_reserve = 2",
        available_for_transfer(charlie_oe) == charlie_oe["quantity"] - charlie_oe["reserved"] - charlie_oe["minimum_reserve"] == 2,
        f"qty={charlie_oe['quantity']} reserved={charlie_oe['reserved']} min={charlie_oe['minimum_reserve']}",
    )
    alpha_fp = InventoryRepository.find("alpha", "FP-102")  # qty 4, reserved 1, min 1
    check("alpha FP-102 transferable = 2", available_for_transfer(alpha_fp) == 4 - 1 - 1)

    # A base holding stock entirely below its minimum reserve must not be
    # offered as a donor.
    InventoryRepository.update(InventoryRepository.find("charlie", "HP-204")["id"], minimum_reserve=2)
    constrained = resource_service.search("WO-1042")
    charlie_row = next((c for c in constrained["candidates"] + constrained["infeasible"] if c["base_id"] == "charlie"), None)
    check(
        "base below its minimum reserve is rejected, not offered",
        charlie_row is not None and charlie_row["feasible"] is False
        and charlie_row["reason"] == "MINIMUM_RESERVE_VIOLATION",
        str(charlie_row.get("reason")) if charlie_row else "missing",
    )
    InventoryRepository.update(InventoryRepository.find("charlie", "HP-204")["id"], minimum_reserve=0)

    # ------------------------------------------------------------------
    section("6. Candidate ranking + expected downtime")
    evaluation = recommendation_service.evaluate_candidates("WO-1042")
    ranked = evaluation["candidates"]
    check("two feasible candidates ranked", len(ranked) == 2, str(len(ranked)))
    check("best is bravo (faster than charlie)", ranked[0]["source_base"] == "bravo", ranked[0]["source_base"])
    check("second is charlie", ranked[1]["source_base"] == "charlie")
    check(
        "scores are descending",
        ranked[0]["score"] >= ranked[1]["score"],
        f"{ranked[0]['score']} vs {ranked[1]['score']}",
    )
    check(
        "bravo expected downtime = 2h ETA + 6h repair",
        ranked[0]["expected_downtime_hours"] == 8.0,
        str(ranked[0]["expected_downtime_hours"]),
    )
    check("charlie expected downtime > bravo", ranked[1]["expected_downtime_hours"] > ranked[0]["expected_downtime_hours"])
    check("objective is minimising fleet downtime", evaluation["objective"] == "MINIMIZE_EXPECTED_FLEET_DOWNTIME")
    # Scores must actually discriminate. An earlier build let penalties swamp
    # the total, pinned every candidate to 0 and left ranking to tiebreakers.
    check(
        "scores discriminate (not all clamped to 0)",
        len({c["score"] for c in ranked}) == len(ranked) and min(c["score"] for c in ranked) > 0,
        str([c["score"] for c in ranked]),
    )
    check(
        "best score is meaningfully ahead of second",
        ranked[0]["score"] - ranked[1]["score"] >= 5,
        f"{ranked[0]['score']} vs {ranked[1]['score']}",
    )
    check(
        "scores stay within 0-100",
        all(0 <= c["score"] <= 100 for c in ranked),
    )
    check(
        "bravo donor impact is LOW (no reserve policy breached)",
        ranked[0]["donor_impact"] == "LOW",
        ranked[0]["donor_impact"],
    )
    check(
        "reason text matches donor impact semantics",
        any("no reserve requirement" in r for r in ranked[0]["reasons"]),
        str(ranked[0]["reasons"]),
    )

    # ------------------------------------------------------------------
    section("7. Recommendation is explainable")
    rec = evaluation["recommended"]
    check("recommendation exists", rec is not None)
    check("recommendation is bravo -> alpha", rec["source_base"] == "bravo" and rec["destination_base"] == "alpha")
    check("has reasons", len(rec.get("reasons", [])) >= 4, str(len(rec.get("reasons", []))))
    check("reasons mention donor reserve", any("reserve" in r.lower() for r in rec["reasons"]))
    check("reasons mention donor impact", any("donor-base impact" in r for r in rec["reasons"]))
    check("donor impact recorded", rec["donor_impact"] in ("VERY LOW", "LOW", "MODERATE", "HIGH"))
    check("fleet impact recorded", rec["fleet_impact"] in ("VERY LOW", "LOW", "MODERATE", "HIGH", "SEVERE"))
    check(
        "infeasible bases reported with a reason",
        all(r.get("reason") for r in evaluation["rejected"]),
    )

    # ------------------------------------------------------------------
    section("8. Decision impact preview")
    impact = impact_service.preview("WO-1042")
    before = availability_service.fleet_overview()["availability_pct"]
    check("preview exposes current availability", "current_fleet_availability_pct" in impact)
    check("preview has both options", len(impact["options"]) == 2)
    check(
        "each option projects a positive availability delta",
        all(o["delta_pct"] > 0 for o in impact["options"]),
        str([o["delta_pct"] for o in impact["options"]]),
    )
    check("preview recommends an option", impact["recommended"]["source_base"] == "bravo")

    baseline_available = availability_service.fleet_overview()["available"]

    # ------------------------------------------------------------------
    section("9. Human approval creates a REAL transfer")
    result = transfer_service.approve_recommendation("WO-1042", actor="commander")
    transfer = result["transfer"]
    check("transfer created", transfer["id"] == "T-103", transfer["id"])
    check("transfer bravo -> alpha", transfer["source_base"] == "bravo" and transfer["dest_base"] == "alpha")
    check("transfer IN_TRANSIT", transfer["status"] == TransferStatus.IN_TRANSIT.value)
    check("transfer tied to the work order", transfer["work_order_id"] == "WO-1042")
    check(
        "bravo stock physically decremented",
        InventoryRepository.find("bravo", "HP-204")["quantity"] == 0,
        str(InventoryRepository.find("bravo", "HP-204")["quantity"]),
    )
    check(
        "work order still waiting on the part",
        WorkOrderRepository.get("WO-1042")["status"] == WorkOrderStatus.WAITING_FOR_RESOURCE.value,
    )
    check(
        "aircraft now WAITING_FOR_PART",
        AircraftRepository_status("A17") == AircraftStatus.WAITING_FOR_PART.value,
        AircraftRepository_status("A17"),
    )

    # ------------------------------------------------------------------
    section("10. Transfer received -> work order resourced")
    transfer_service.receive_transfer("T-103", actor="logistics")
    check(
        "alpha now holds HP-204",
        InventoryRepository.find("alpha", "HP-204")["quantity"] == 1,
        str(InventoryRepository.find("alpha", "HP-204")["quantity"]),
    )
    check(
        "work order is RESOURCE_AVAILABLE",
        WorkOrderRepository.get("WO-1042")["status"] == WorkOrderStatus.RESOURCE_AVAILABLE.value,
    )

    # ------------------------------------------------------------------
    section("11. Maintenance executed")
    started = maintenance_service.start_maintenance("WO-1042", actor="base")
    check("work order IN_PROGRESS", started["status"] == WorkOrderStatus.IN_PROGRESS.value)
    check("aircraft in MAINTENANCE", AircraftRepository_status("A17") == AircraftStatus.MAINTENANCE.value)

    # Refuse to start twice / wrong sequence is enforced by status checks.
    check(
        "cannot complete a work order that never started",
        _completion_guard_works(),
    )

    completed = maintenance_service.complete_maintenance("WO-1042", actor="base")
    check("work order COMPLETED", completed["status"] == WorkOrderStatus.COMPLETED.value)
    check("aircraft AVAILABLE", AircraftRepository_status("A17") == AircraftStatus.AVAILABLE.value)
    check(
        "consumed component removed from alpha stock",
        InventoryRepository.find("alpha", "HP-204")["quantity"] == 0,
        str(InventoryRepository.find("alpha", "HP-204")["quantity"]),
    )
    check("predicted event resolved", EventRepository.get("PM-001")["status"] == MaintenanceEventStatus.RESOLVED.value)

    # ------------------------------------------------------------------
    section("12. Availability recalculated automatically")
    after = availability_service.fleet_overview()
    check(
        "available count increased",
        after["available"] == baseline_available + 1,
        f"{baseline_available} -> {after['available']}",
    )
    check(
        "availability_pct is derived, not stored",
        after["availability_pct"] == round(after["available"] / after["total"] * 100, 1),
        f"{after['availability_pct']} vs {after['available']}/{after['total']}",
    )
    check(
        "A17 counted as flyable",
        sum(1 for a in availability_aircraft() if a["id"] == "A17" and a["status"] == "AVAILABLE") == 1,
    )

    # ------------------------------------------------------------------
    section("13. Audit trail recorded the whole loop")
    audit_types = {r["event_type"] for r in audit_service.timeline()}
    for expected in (
        "PREDICTION_GENERATED",
        "MAINTENANCE_EVENT_CREATED",
        "WORK_ORDER_CREATED",
        "RECOMMENDATION_GENERATED",
        "RECOMMENDATION_APPROVED",
        "TRANSFER_CREATED",
        "TRANSFER_STARTED",
        "TRANSFER_RECEIVED",
        "MAINTENANCE_STARTED",
        "MAINTENANCE_COMPLETED",
        "AIRCRAFT_RETURNED_TO_SERVICE",
        "WORK_ORDER_STATUS_CHANGED",
    ):
        check(f"audit has {expected}", expected in audit_types)

    wo_trail = audit_service.timeline(entity_id="WO-1042")
    check("work order has a chronological trail", len(wo_trail) >= 6, str(len(wo_trail)))

    # ------------------------------------------------------------------
    section("14. Prediction history available")
    history = maintenance_service.prediction_history("A17")
    check("history has entries", len(history) > 0)
    check("history is ordered oldest first", history == sorted(history, key=lambda h: h["timestamp"]))
    check("history shows declining health", history[0]["health_score"] > history[-1]["health_score"],
          f"{history[0]['health_score']} -> {history[-1]['health_score']}")
    check("history ends at current health", history[-1]["health_score"] == 41, str(history[-1]["health_score"]))

    # ------------------------------------------------------------------
    section("15. Reserve override requires explicit authorisation")
    # Pin charlie's HP-204 reserve so moving one unit WOULD break it.
    InventoryRepository.update(InventoryRepository.find("charlie", "HP-204")["id"], minimum_reserve=2)
    transfer_service.create_transfer("HP-204", "charlie", "alpha", quantity=1)
    try:
        transfer_service.approve_transfer("T-104")
        check("unauthorised reserve violation blocked", False, "approval unexpectedly succeeded")
    except transfer_service.TransferError as exc:
        check("unauthorised reserve violation blocked", "minimum reserve" in str(exc).lower(), str(exc))
    transfer_service.approve_transfer("T-104", actor="commander", allow_reserve_override=True)
    check("authorised override succeeds", TransferRepository.get("T-104")["status"] == TransferStatus.IN_TRANSIT.value)
    check(
        "override is written to the audit trail",
        "RESERVE_OVERRIDE_APPLIED" in {r["event_type"] for r in audit_service.timeline()},
    )

    # ------------------------------------------------------------------
    section("16. Demo reset restores the scenario")
    reset()
    availability_service.sync_aircraft_states()
    check("A17 back to WAITING_FOR_PART scenario", WorkOrderRepository.get("WO-1042")["status"] == WorkOrderStatus.WAITING_FOR_RESOURCE.value)
    check("bravo HP-204 restored", InventoryRepository.find("bravo", "HP-204")["quantity"] == 1)
    check("A17 not AVAILABLE", AircraftRepository_status("A17") != AircraftStatus.AVAILABLE.value)

    print(f"\n{'=' * 60}")
    print(f"{PASSED} passed, {len(FAILED)} failed")
    for f in FAILED:
        print(f"  FAILED: {f}")
    return 1 if FAILED else 0


def AircraftRepository_status(aircraft_id: str) -> str:
    from app.repositories import AircraftRepository
    ac = AircraftRepository.get(aircraft_id)
    return ac["status"] if ac else ""


def availability_aircraft():
    from app.repositories import AircraftRepository
    return AircraftRepository.list_all()


def _completion_guard_works() -> bool:
    """A waiting work order cannot start or complete maintenance."""
    guard = WorkOrderRepository.create(
        # A28 is already grounded in the seed, so this guard probe does not
        # alter the fleet's available-aircraft count during the main workflow.
        aircraft_id="A28", base_id="bravo", priority="LOW", source="MANUAL",
        predicted_event_id=None, issue="guard", maintenance_action="guard",
        required_component="AV-077",
        status=WorkOrderStatus.WAITING_FOR_RESOURCE.value,
        estimated_repair_hours=1.0, required_by_flight_hours=None,
        created_at="", updated_at="", started_at=None, completed_at=None,
    )
    try:
        maintenance_service.start_maintenance(guard["id"], actor="base")
        return False
    except ValueError:
        pass
    try:
        maintenance_service.complete_maintenance(guard["id"], actor="base")
        return False
    except ValueError:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
