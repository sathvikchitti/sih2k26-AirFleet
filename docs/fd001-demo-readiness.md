# FD001 demo workflow readiness

This is an API-level demonstration of the local FD001 model integrated with the in-memory maintenance workflow. It uses simulated NASA C-MAPSS engine histories, not aircraft telemetry. The repeatable PowerShell runner is `backend/scripts/fd001_demo_readiness.ps1`; it resets only the server passed through `-BaseUrl`, so use an isolated demo server.

## Connected flow and manual steps

`GET /api/health/A21` returns the current provider prediction. On the verified local artifact, A21 maps to simulated engine 3 and returned model `cmapss-fd001-rf-v1`, RUL 52.2867 cycles, derived risk `CRITICAL`, `failure_probability: null`, no subsystem, and `is_synthetic: true`. Health/risk are derived presentation values; they are not a calibrated failure probability. Cycle RUL does not populate a flight-hour or calendar deadline.

The connected workflow supports role-gated prediction ingestion (`POST /api/aircraft/A21/predict`), resource search, candidate evaluation, Commander rejection/approval, Logistics receipt, and Base Manager maintenance start/completion. Prediction ingestion records a prediction-history row and creates or updates an unresolved event. It does not create a work order. Repeating ingestion reuses the same unresolved event but records another history row for each request; there is no request-level exactly-once key. Repeating triage on an event already linked to a work order returns that same work order. Once an event is resolved, a later explicit prediction can create a new open event. Direct manual work-order creation remains a separate operation and is not globally deduplicated.

FD001 does not predict a subsystem or part. A human must use `POST /api/maintenance/events/{event_id}/work-order` with a catalogued `required_component` before resource search and candidate evaluation. The UI currently lacks this event-triage action, so this part of the FD001 flow requires an API client. For known maintenance rules, the service restricts operator selection to the rule's component candidates. For an unmatched FD001 event, it accepts a catalogued human choice; the project has no aircraft-specific engineering compatibility or airworthiness data to validate that choice.

Recommendation rejection (`POST /api/recommendations/{aircraft_id}/reject`) is currently audit-only: it creates no transfer and causes no inventory movement, but it does not persist a terminal decision. The same work order may later be explicitly approved by a Commander. Commander approval dispatches the selected transfer directly to `IN_TRANSIT`; no separate Logistics approval is part of this route. Logistics receipt increments destination stock. Base Manager maintenance reserves and consumes the received unit. Approval retries return the active in-transit transfer and are rejected after receipt or when the work order has moved beyond the eligible open/waiting states.

## Verified isolated run

From `backend/`, start a fresh local server on port 8002 with the trained artifact and FD001 provider:

```powershell
$env:ML_PROVIDER = 'fd001'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

In another PowerShell window, run:

```powershell
pwsh -NoProfile -File .\scripts\fd001_demo_readiness.ps1 -BaseUrl http://127.0.0.1:8002
```

The script uses existing API schemas and caller-selected demo role headers. It resets the isolated server, confirms a wrong-role prediction request is forbidden, and asserts the aircraft/event/work-order references, cycle units, null probability, synthetic provenance, candidate stock/condition constraints, rejection effect, transfer stock deltas, and maintenance lifecycle. It reports measured counts and IDs as JSON. On the recorded run, the selected transfer moved one HP-204 from bravo (1→0) to alpha (0→1 on receipt), then maintenance consumed it (1→0). Fleet available count was 6 before, during, and after; fleet maintenance count changed 0→1→0. A21 remained `AT_RISK` because completing the work order does not advance the fixed simulated history or provide post-repair telemetry. These results verify workflow mechanics, not predictive recovery.

API role headers such as `X-Demo-Role` and `X-Demo-Base` are caller-provided demo claims, not authenticated identity. Do not expose the demo server as a production authorization boundary. The app's default provider remains mock unless `ML_PROVIDER=fd001` is explicitly selected.
