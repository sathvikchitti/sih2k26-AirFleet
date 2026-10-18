"""Regression guard: the 21 original POC endpoints must keep working.

The existing frontend (which is not being redesigned) depends on these paths
and field names. This script asserts each one returns its original shape.

Run with the backend running on :8000 —  python tests/test_api_compat.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
PASSED = 0
FAILED: list[str] = []


def call(path: str, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if condition:
        PASSED += 1
        print(f"  PASS  {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL  {label}{('  <- ' + detail) if detail else ''}")


def has_keys(row: dict, *keys) -> bool:
    return all(k in row for k in keys)


def main() -> int:
    # Reset first so the run is order-independent.
    call("/api/demo/reset", "POST")

    print("\n=== GET endpoints")
    status, fleet = call("/api/fleet/overview")
    check("GET /api/fleet/overview -> 200", status == 200)
    check("fleet has total/available/availability_pct/bases",
          has_keys(fleet, "total", "available", "availability_pct", "bases"))
    check("fleet keeps legacy keys (maintenance, at_risk, high_risk)",
          has_keys(fleet, "maintenance", "at_risk", "high_risk"))

    status, bases = call("/api/bases")
    check("GET /api/bases -> 3 bases with aircraft lists",
          status == 200 and len(bases) == 3 and has_keys(bases[0], "id", "name", "aircraft"))

    status, ac = call("/api/aircraft")
    check("GET /api/aircraft -> 10 aircraft", status == 200 and len(ac) == 10)
    check("aircraft row keeps legacy shape",
          has_keys(ac[0], "id", "base_id", "type", "tail", "status",
                   "required_component", "health", "maintenance"))
    check("health block keeps ML contract fields",
          has_keys(ac[0]["health"], "health_score", "failure_probability", "rul",
                   "confidence", "risk_level", "predicted_maintenance"))
    check("A17 still reports HP-204 via the knowledge layer",
          next(a for a in ac if a["id"] == "A17")["required_component"] == "HP-204")

    status, detail = call("/api/aircraft/A17")
    check("GET /api/aircraft/A17 -> 200", status == 200)
    check("detail keeps resource_availability + recommendation",
          has_keys(detail, "resource_availability", "recommendation", "trend", "maintenance"))
    check("resource rows keep legacy fields",
          has_keys(detail["resource_availability"][0], "base_id", "quantity", "condition_pct",
                   "distance_km", "eta_hours", "status"))
    check("detail adds new-model extras",
          has_keys(detail, "work_orders", "predicted_events", "prediction_history"))

    status, missing = call("/api/aircraft/NOPE")
    check("GET /api/aircraft/NOPE -> 404", status == 404)

    status, hp = call("/api/health/A17")
    check("GET /api/health/A17 -> 200", status == 200)
    check("health keeps the ML contract",
          has_keys(hp, "aircraft_id", "timestamp", "health_score", "failure_probability",
                   "rul", "confidence", "risk_level"))
    check("health exposes knowledge-derived maintenance view",
          has_keys(hp, "maintenance"))
    check("ML payload still carries required_component for the old UI",
          hp.get("required_component") == "HP-204")

    status, allh = call("/api/health")
    check("GET /api/health -> 10 predictions", status == 200 and len(allh) == 10)

    status, trend = call("/api/aircraft/A17/trend")
    check("GET /api/aircraft/A17/trend -> {aircraft_id, trend}",
          status == 200 and has_keys(trend, "aircraft_id", "trend"))

    status, inv = call("/api/inventory")
    check("GET /api/inventory -> 10 lines", status == 200 and len(inv) == 10)
    check("inventory row keeps legacy fields",
          has_keys(inv[0], "id", "base_id", "part_number", "quantity", "reserved",
                   "condition_pct", "status"))
    check("inventory exposes reserve-aware fields",
          has_keys(inv[0], "reserved_quantity", "minimum_reserve", "available_for_transfer"))

    status, parts = call("/api/parts")
    check("GET /api/parts -> 4 parts", status == 200 and len(parts) == 4)
    check("part keeps legacy fields",
          has_keys(parts[0], "part_number", "name", "category", "min_condition_pct"))

    status, mx = call("/api/maintenance")
    check("GET /api/maintenance -> legacy rows", status == 200 and len(mx) >= 4)
    check("maintenance row keeps legacy shape",
          has_keys(mx[0], "id", "aircraft_id", "component", "priority", "status",
                   "estimated_recovery_hours", "started"))

    status, transfers = call("/api/transfers")
    check("GET /api/transfers -> 2 transfers", status == 200 and len(transfers) == 2)
    check("transfer keeps legacy fields",
          has_keys(transfers[0], "id", "part_number", "source_base", "dest_base",
                   "quantity", "status", "eta_hours"))

    status, rec = call("/api/recommendations/A17")
    check("GET /api/recommendations/A17 -> 200", status == 200)
    check("recommendation keeps legacy shape",
          has_keys(rec, "aircraft_id", "home_base", "required_component", "urgency",
                   "risk_level", "rul", "candidates", "recommended"))
    check("candidate keeps legacy fields",
          has_keys(rec["candidates"][0], "donor_base", "quantity_available", "condition_pct",
                   "distance_km", "eta_hours", "retains_reserve", "reserve_violation",
                   "expected_downtime_hours", "score"))
    check("recommended carries reasons for the UI", len(rec["recommended"].get("reasons", [])) > 0)
    check("recommendation is bravo -> alpha (unchanged demo outcome)",
          rec["recommended"]["donor_base"] == "bravo")

    status, dist = call("/api/demo/distances")
    check("GET /api/demo/distances -> 200", status == 200 and "alpha-bravo" in dist)

    print("\n=== New-model endpoints")
    status, events = call("/api/maintenance/events")
    check("GET /api/maintenance/events -> predicted events", status == 200 and len(events) >= 5)
    check("event carries the documented fields",
          has_keys(events[0], "id", "aircraft_id", "prediction_id", "predicted_issue",
                   "subsystem", "risk_level", "rul", "confidence", "predicted_time",
                   "required_resource_type", "status", "created_at"))

    status, wos = call("/api/maintenance/work-orders")
    check("GET /api/maintenance/work-orders -> 200", status == 200)
    check("work order carries the documented fields",
          has_keys(wos[0], "id", "aircraft_id", "base_id", "priority", "source",
                   "predicted_event_id", "issue", "required_component", "status",
                   "estimated_repair_hours", "created_at", "updated_at"))

    status, search = call("/api/resources/search/WO-1042")
    check("GET /api/resources/search/WO-1042 -> 200", status == 200)
    check("search reports feasible + infeasible with reasons",
          "candidates" in search and "infeasible" in search)

    status, impact = call("/api/work-orders/WO-1042/impact")
    check("GET /api/work-orders/WO-1042/impact -> 200", status == 200)
    check("impact preview exposes options + delta",
          has_keys(impact, "current_fleet_availability_pct", "options") and
          has_keys(impact["options"][0], "source_base", "expected_fleet_availability_pct", "delta_pct"))

    status, hist = call("/api/predictions/A17/history")
    check("GET /api/predictions/A17/history -> 200", status == 200 and hist["count"] > 0)
    check("history rows carry time/health/risk/rul",
          has_keys(hist["predictions"][0], "timestamp", "health_score", "risk_level", "rul"))

    status, audit = call("/api/audit")
    check("GET /api/audit -> 200", status == 200 and audit["count"] > 0)
    check("audit rows are generic events",
          has_keys(audit["events"][0], "id", "event_type", "occurred_at", "entity_type",
                   "entity_id", "summary", "actor"))

    status, perms = call("/api/audit/permissions")
    check("GET /api/audit/permissions -> three roles",
          status == 200 and set(perms) == {"commander", "base", "logistics"})

    status, know = call("/api/maintenance/knowledge")
    check("GET /api/maintenance/knowledge -> issue/action/components mapping",
          status == 200 and has_keys(know["rules"][0], "issue", "maintenance_action",
                                     "candidate_components"))

    print("\n=== Mutating endpoints (legacy paths)")
    status, created = call("/api/transfers", "POST",
                           {"part_number": "OE-310", "source_base": "charlie",
                            "dest_base": "alpha", "quantity": 1})
    check("POST /api/transfers -> 200", status == 200)
    check("created transfer is PENDING_APPROVAL", created["status"] == "PENDING_APPROVAL")

    status, approved = call(f"/api/transfers/{created['id']}/approve", "POST", {})
    check("POST /api/transfers/{id}/approve -> IN_TRANSIT",
          status == 200 and approved["status"] == "IN_TRANSIT")

    status, received = call(f"/api/transfers/{created['id']}/receive", "POST")
    check("POST /api/transfers/{id}/receive -> RECEIVED",
          status == 200 and received["status"] == "RECEIVED")

    # The closed loop through legacy paths: approve recommendation -> receive
    # -> start -> complete -> availability moves.
    status, before = call("/api/fleet/overview")
    baseline_available = before["available"]

    status, approval = call("/api/recommendations/A17/approve", "POST", {"actor": "commander"})
    check("POST /api/recommendations/A17/approve -> transfer created", status == 200 and "transfer" in approval)
    transfer_id = approval["transfer"]["id"]
    check("approval marks the transfer IN_TRANSIT", approval["transfer"]["status"] == "IN_TRANSIT")

    status, detail = call("/api/aircraft/A17")
    check("legacy detail reports AWAITING_DELIVERY while in transit",
          detail["maintenance"]["status"] == "AWAITING_DELIVERY",
          str(detail["maintenance"]["status"]))

    call(f"/api/transfers/{transfer_id}/receive", "POST")
    status, detail = call("/api/aircraft/A17")
    check("legacy detail reports READY_TO_START once received",
          detail["maintenance"]["status"] == "READY_TO_START",
          str(detail["maintenance"]["status"]))

    status, _ = call("/api/maintenance/A17/start", "POST")
    check("POST /api/maintenance/A17/start -> 200", status == 200)
    status, _ = call("/api/maintenance/A17/complete", "POST")
    check("POST /api/maintenance/A17/complete -> 200", status == 200)

    status, after = call("/api/fleet/overview")
    check("fleet availability recalculated after the loop",
          after["available"] == baseline_available + 1,
          f"{baseline_available} -> {after['available']}")
    check("A17 is AVAILABLE after the loop",
          next(a for a in call("/api/aircraft")[1] if a["id"] == "A17")["status"] == "AVAILABLE")

    status, _ = call("/api/demo/reset", "POST")
    status, fleet = call("/api/fleet/overview")
    check("POST /api/demo/reset restores deterministic state",
          status == 200 and fleet["total"] == 10)

    print(f"\n{'=' * 60}")
    print(f"{PASSED} passed, {len(FAILED)} failed")
    for f in FAILED:
        print(f"  FAILED: {f}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())