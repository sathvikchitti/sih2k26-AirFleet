#!/usr/bin/env python3
"""Exercise the FD001 demo API end to end on an explicitly selected instance.

This script never resets state. Mutating operations require the explicit
``--allow-demo-mutations`` switch and are restricted to loopback URLs.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

_CALL_LOG: list[dict] = []


def request_json(base_url: str, path: str, *, method: str = "GET",
                 body: dict | None = None, role: str | None = None,
                 base: str | None = None):
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if role:
        headers["X-Demo-Role"] = role
    if base:
        headers["X-Demo-Base"] = base
    _CALL_LOG.append({"method": method, "path": path, "role": role or "read-only", "base": base})
    request = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def stock_line(rows: list[dict], base: str, part_number: str) -> dict | None:
    row = next((item for item in rows
                if str(item.get("base_id", "")).lower() == base.lower()
                and str(item.get("part_number", "")).upper() == part_number.upper()), None)
    if row is None:
        return None
    return {
        "quantity": row.get("quantity"),
        "reserved": row.get("reserved_quantity", row.get("reserved")),
        "minimum_reserve": row.get("minimum_reserve"),
        "available_for_transfer": row.get("available_for_transfer"),
        "condition_pct": row.get("condition_pct"),
    }


def health_signature(detail: dict) -> dict:
    health = detail.get("health") or {}
    return {key: health.get(key) for key in (
        "health_score", "rul", "rul_unit", "failure_probability", "model_version",
    )}


def fleet_signature(payload: dict) -> dict:
    return {key: payload.get(key) for key in ("total", "available", "availability_pct")}


def main() -> int:
    _CALL_LOG.clear()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="explicit disposable demo URL, e.g. http://127.0.0.1:8013")
    parser.add_argument(
        "--allow-demo-mutations", action="store_true",
        help="authorize the scripted transfer, approval, receipt, triage, and maintenance calls",
    )
    args = parser.parse_args()
    parts = urlsplit(args.base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.path not in {"", "/"}:
        parser.error("--base-url must be an absolute HTTP(S) origin without an API path")
    if args.allow_demo_mutations and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("mutating rehearsal is restricted to a loopback --base-url")

    base_url = args.base_url.rstrip("/")
    manifest = request_json(base_url, "/api/demo/scenario")
    require(isinstance(manifest, dict), "scenario endpoint did not return an object")
    require(manifest.get("scenario_id") == "fd001_operations_v1",
            "refusing to continue: API is not the expected fd001_operations_v1 scenario")
    require(manifest.get("model_provider") == "fd001-random-forest",
            "refusing to continue: selected provider is not FD001")
    scenarios = {row["id"]: row for row in manifest.get("scenarios", [])}
    require("B" in scenarios, "scenario manifest does not include canonical case B")

    aircraft = request_json(base_url, "/api/aircraft")
    require(isinstance(aircraft, list) and aircraft, "aircraft API returned no rows")
    require(all(row.get("health", {}).get("rul_unit") == "cycles"
                and row.get("health", {}).get("failure_probability") is None
                for row in aircraft),
            "aircraft health payload does not preserve FD001 cycle units and unavailable probability")

    forecast = request_json(base_url, "/api/resources/forecast?horizon_cycles=60")
    require(forecast.get("horizon_cycles") == 60.0 and forecast.get("mutated_state") is False,
            "cycle forecast did not return the expected read-only 60-cycle contract")
    moves = [row for row in forecast.get("suggested_moves", [])
             if row.get("action") == "create_transfer" and row.get("feasible") is True
             and int(row.get("quantity", 0)) > 0]
    report = {
        "scenario_id": manifest["scenario_id"],
        "model_version": manifest.get("model_version"),
        "aircraft_count": len(aircraft),
        "health_contract": "cycles with null failure_probability",
        "forecast": {
            "horizon_cycles": forecast["horizon_cycles"],
            "eligible_prediction_count": forecast.get("eligible_prediction_count"),
            "suggested_move_count": len(moves),
            "sample_moves": moves[:3],
        },
        "mutations_run": False,
        "api_calls": list(_CALL_LOG),
    }
    if not args.allow_demo_mutations:
        print(json.dumps(report, indent=2, sort_keys=True))
        print("Read-only preflight complete. Re-run with --allow-demo-mutations on a disposable loopback instance.")
        return 0
    require(moves, "forecast returned no feasible suggested move; no mutation was attempted")

    # Keep the forecast-driven transfer unbound. The forecast is a planning
    # suggestion, not an aircraft diagnosis or a work-order authorization.
    move = next((row for row in moves if row.get("part_number") == "HP-204"
                 and row.get("source_base") == "charlie"
                 and row.get("destination_base") == "bravo"), moves[0])
    fleet_before = request_json(base_url, "/api/fleet/overview")
    fleet_before_signature = fleet_signature(fleet_before)
    aircraft_id = scenarios["B"]["aircraft_id"]
    aircraft_before = request_json(base_url, f"/api/aircraft/{aircraft_id}")
    health_before = health_signature(aircraft_before)
    initial_inventory = request_json(base_url, "/api/inventory")
    forecast_stock_before = {
        "source": stock_line(initial_inventory, move["source_base"], move["part_number"]),
        "destination": stock_line(initial_inventory, move["destination_base"], move["part_number"]),
    }
    request = request_json(
        base_url, "/api/transfers", method="POST",
        body={
            "part_number": move["part_number"],
            "source_base": move["source_base"],
            "dest_base": move["destination_base"],
            "quantity": int(move["quantity"]),
            "actor": "logistics",
        }, role="logistics",
    )
    require(request.get("status") == "PENDING_APPROVAL",
            "Logistics forecast transfer request was not pending approval")
    forecast_transfer_id = request["id"]
    dispatched = request_json(
        base_url, f"/api/transfers/{forecast_transfer_id}/approve", method="POST",
        body={"actor": "logistics"}, role="logistics",
    )
    require(dispatched.get("status") == "IN_TRANSIT",
            "Logistics approval did not dispatch the forecast transfer")
    received_forecast = request_json(
        base_url, f"/api/transfers/{forecast_transfer_id}/receive?actor=logistics",
        method="POST", role="logistics",
    )
    require(received_forecast.get("status") == "RECEIVED",
            "Logistics receipt did not complete the forecast transfer")
    forecast_inventory_after = request_json(base_url, "/api/inventory")
    forecast_stock_after = {
        "source": stock_line(forecast_inventory_after, move["source_base"], move["part_number"]),
        "destination": stock_line(forecast_inventory_after, move["destination_base"], move["part_number"]),
    }

    # Case B is already triaged by the opt-in fixture. POSTing the same event
    # and human-selected component exercises the idempotent API response; this
    # report deliberately does not claim the rehearsal created a new WO.
    case = scenarios["B"]
    aircraft_id = case["aircraft_id"]
    work_order_id = case["work_order_id"]
    event_id = case["event_id"]
    before_order = request_json(base_url, f"/api/maintenance/work-orders/{work_order_id}")
    require(before_order.get("aircraft_id") == aircraft_id,
            "fixture work order does not match scenario B aircraft")
    component = before_order.get("required_component")
    event = request_json(base_url, f"/api/maintenance/events/{event_id}")
    triaged = request_json(
        base_url, f"/api/maintenance/events/{event_id}/work-order", method="POST",
        body={"required_component": component, "actor": "base"},
        role="base", base=before_order["base_id"],
    )
    require(triaged.get("id") == work_order_id,
            "event triage did not return the already-linked scenario B work order")
    recommendation = request_json(
        base_url, f"/api/work-orders/{work_order_id}/recommendation",
    )
    require(recommendation.get("recommended") is not None,
            "scenario B has no feasible recommendation to approve")
    maintenance_source = recommendation["recommended"]["source_base"]
    maintenance_destination = before_order["base_id"]
    maintenance_inventory_before = request_json(base_url, "/api/inventory")
    maintenance_stock_before = {
        "source": stock_line(maintenance_inventory_before, maintenance_source, component),
        "destination": stock_line(maintenance_inventory_before, maintenance_destination, component),
    }
    approval = request_json(
        base_url, f"/api/work-orders/{work_order_id}/recommendation/approve",
        method="POST", body={"actor": "commander"}, role="commander",
    )
    maintenance_transfer = approval.get("transfer") or {}
    require(maintenance_transfer.get("status") == "IN_TRANSIT",
            "Commander recommendation approval did not dispatch the maintenance transfer")
    maintenance_transfer_id = maintenance_transfer["id"]
    landed = request_json(
        base_url, f"/api/transfers/{maintenance_transfer_id}/receive?actor=logistics",
        method="POST", role="logistics",
    )
    require(landed.get("status") == "RECEIVED",
            "Logistics did not receive the maintenance resource")
    available_order = request_json(base_url, f"/api/maintenance/work-orders/{work_order_id}")
    require(available_order.get("status") == "RESOURCE_AVAILABLE",
            "receipt did not make the linked work order resource-available")
    started = request_json(
        base_url, f"/api/maintenance/work-orders/{work_order_id}/start?actor=base",
        method="POST", role="base", base=before_order["base_id"],
    )
    require(started.get("status") == "IN_PROGRESS", "Base Manager could not start maintenance")
    completed = request_json(
        base_url, f"/api/maintenance/work-orders/{work_order_id}/complete?actor=base",
        method="POST", role="base", base=before_order["base_id"],
    )
    require(completed.get("status") == "COMPLETED", "Base Manager could not complete maintenance")
    final_aircraft = request_json(base_url, f"/api/aircraft/{aircraft_id}")
    health_after = health_signature(final_aircraft)
    require(health_after == health_before,
            "aircraft health prediction changed during the operational workflow")
    final_inventory = request_json(base_url, "/api/inventory")
    maintenance_stock_after = {
        "source": stock_line(final_inventory, maintenance_source, component),
        "destination": stock_line(final_inventory, maintenance_destination, component),
    }
    fleet_after = request_json(base_url, "/api/fleet/overview")
    timeline = request_json(
        base_url, f"/api/aircraft/{aircraft_id}/maintenance-timeline?{urlencode({'work_order_id': work_order_id})}",
    )
    require(timeline.get("mutated_state") is False,
            "maintenance timeline GET did not declare read-only behavior")

    report.update({
        "mutations_run": True,
        "forecast_transfer": {
            "id": forecast_transfer_id,
            "part_number": move["part_number"],
            "source_base": move["source_base"],
            "destination_base": move["destination_base"],
            "quantity": int(move["quantity"]),
            "linkage": "unbound forecast suggestion; no aircraft diagnosis claimed",
            "status": received_forecast["status"],
            "actors": ["logistics", "logistics"],
            "stock_before": forecast_stock_before,
            "stock_after": forecast_stock_after,
        },
        "maintenance_case": {
            "aircraft_id": aircraft_id,
            "event_id": event_id,
            "event_status_before_triage_call": event.get("status"),
            "triage_result": "returned existing fixture work order; no new WO claimed",
            "work_order_id": work_order_id,
            "component": component,
            "component_source": triaged.get("component_source"),
            "recommendation_source": recommendation["recommended"].get("source_base"),
            "transfer_id": maintenance_transfer_id,
            "transfer_status": landed["status"],
            "work_order_status": completed["status"],
            "timeline_linkage": timeline.get("linkage"),
            "availability_after_completion": final_aircraft.get("status"),
            "actors": ["base", "commander", "logistics", "base"],
            "health_before": health_before,
            "health_after": health_after,
            "health_prediction_unchanged": health_before == health_after,
            "stock_before": maintenance_stock_before,
            "stock_after": maintenance_stock_after,
        },
        "fleet_availability_before": fleet_before_signature,
        "fleet_availability_after": fleet_signature(fleet_after),
        "api_calls": list(_CALL_LOG),
    })
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        print(f"Rehearsal stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
