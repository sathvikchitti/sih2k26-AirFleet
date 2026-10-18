# FD001 demo blocker verification

Read-only checks and the narrow regression correction for the local FD001 demo on 2026-10-17.

## Findings

- Port `8002` had no listener when first inspected. Port `8006` was serving FD001: health, timeline, and resource-demand GETs returned 200, but its CORS allowlist contained only `http://127.0.0.1:5174`. Consequently an OPTIONS preflight with `Origin: http://localhost:5174` returned 400; the `127.0.0.1` origin returned 200. No GET or OPTIONS request mutates demo state.
- A fresh isolated server was started on `127.0.0.1:8002` with both frontend origins allowed. On this server, health, timeline, and resource-demand GETs returned 200; both origin preflights returned 200 with the matching `Access-Control-Allow-Origin`. A21 reported provider `fd001-random-forest`, model `cmapss-fd001-rf-v1`, RUL `52.2866804861805` cycles, null failure probability, and synthetic history. Initial state had one A21 event and no work orders.
- `test_training_is_grouped_reproducible_and_round_trips_artifact` compared the entire second loaded-model prediction dict by exact equality. The correction applies `pytest.approx(rel=1e-12, abs=1e-12)` only to numeric `rul_cycles`; all other prediction metadata and categories remain exact-equality assertions. The repeated training-metrics dict comparison remains exact.

## Commands and results

From `E:\Projects\Air fleet\backend`:

```powershell
python -m pytest -q
# 78 passed in 28.40s (elevated execution)

python -m pytest -q --basetemp .pytest-tmp
# 78 passed in 28.80s

python -m tests.test_workflow
# 103 passed, 0 failed
```

The sandboxed pytest attempt could not create its default temporary directory. The suite was rerun with the workspace-local basetemp and elevated execution required for this Windows test environment.

The fresh isolated backend was started with:

```powershell
Set-Location 'E:\Projects\Air fleet\backend'
$env:ML_PROVIDER = 'fd001'
Remove-Item Env:DEMO_SCENARIO -ErrorAction SilentlyContinue
$env:FRONTEND_ORIGINS = 'http://localhost:5174,http://127.0.0.1:5174'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Diagnostic GET and OPTIONS probes returned 200 on port 8002. The server is process 3412. No reset was sent. The browser flow below created and advanced the demo work order and transfer on 8002. No writes were sent to ports 8006, 8000, or 5173.

## Browser flow and final read-only state

The browser used `http://localhost:5174` with its API proxy targeting port 8002. The user-visible flow loaded A21's FD001 prediction and PM-001 timeline, then a Base Manager selected HP-204 for the event, Commander approved transfer T-103 from Bravo to Alpha, Logistics received it, and Base Manager started and completed WO-1046. The browser showed API HTTP 200 on the maintenance timeline. A21 remained AT_RISK at 52.29 cycles after completion; the static FD001 history does not provide post-maintenance telemetry.

Final read-only API checks on port 8002 returned 200:

- `GET /api/health/A21`: provider `fd001-random-forest`, model `cmapss-fd001-rf-v1`, RUL `52.2866804861805` cycles, null failure probability, risk `CRITICAL`, synthetic history.
- `GET /api/aircraft/A21/maintenance-timeline`: PM-001 links to WO-1046. The work order is `COMPLETED`, explicitly records `component_source=human_selected`, has `required_by_flight_hours:null`, and records `required_by_rul=52.2866804861805`, `rul_unit=cycles`. T-103 is `RECEIVED`, Bravo→Alpha, linked to WO-1046.
- `GET /api/resources/demand`: HP-204 quantity and reservation are both 0 at Alpha and Bravo; Charlie has quantity 2, reserved 0. The separate fleet overview returned 10 total, 6 available, 0 in maintenance, 0 waiting for part, and 4 at risk.

Screenshots from the browser rehearsal: [FD001 prediction](C:/Users/bhanodai/.codex/visualizations/2026/10/17/01a14810-55e6-7001-a1e6-028b5b5ebfde/a21-fd001-fixed.jpg) and [maintenance timeline](C:/Users/bhanodai/.codex/visualizations/2026/10/17/01a14810-55e6-7001-a1e6-028b5b5ebfde/a21-timeline-fixed.jpg).

The trained artifact SHA256 before and after is `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`; it was not retrained or modified.

Backend file changed for this blocker: `backend/tests/test_fd001_model.py`.

## Frontend verification

The original frontend session had been compiled with a stale direct `VITE_API_BASE=http://127.0.0.1:8006`. That bypassed Vite's same-origin proxy and caused the localhost browser origin to fail the backend's CORS preflight. The frontend now defaults its `/api` proxy to `http://127.0.0.1:8002`, while an explicitly configured `VITE_API_BASE` remains supported. The render-only SSR harness leaves that base empty so deterministic offline fixtures can render without a backend.

The API layer treats HTTP errors and explicit direct API failures as live-provider errors; it does not substitute bundled data for an HTTP 503. Same-origin network failures may use the existing complete bundled demo fallback, whose health prediction is visibly labeled offline/illustrative. Aircraft detail provenance is based on the displayed health snapshot rather than a global request flag. The footer reports the latest actual API response, including HTTP errors separately from no response. Resource distance and ETA show an em dash when the API omits those fields, while preserving valid zero values. Null FD001 probability/confidence/subsystem/horizon fields remain unavailable, cycles remain cycles, and the CRITICAL health-only risk band is identified as uncalibrated.

Frontend files changed for the demo blocker work:

- `frontend/vite.config.js` — configurable same-origin proxy target, defaulting to port 8002.
- `frontend/vite.render-check.config.js` — empty API base for deterministic offline SSR checks.
- `frontend/src/services/api.js` — strict API-vs-network fallback behavior, request status tracking, and null-safe resource text formatters.
- `frontend/src/components/Shell.jsx` — actual last-response status in the footer, without a global health-fallback claim.
- `frontend/src/pages/AircraftDetail.jsx` — snapshot-specific offline provenance, FD001 risk-band clarification, and null-safe resource display.
- `frontend/scripts/prediction-contract.test.mjs` — focused dependency-free contract test added by the workflow reviewer.

The isolated frontend was run from `E:\Projects\Air fleet\frontend` with:

```powershell
Remove-Item Env:VITE_API_BASE -ErrorAction SilentlyContinue
$env:API_PROXY_TARGET = 'http://127.0.0.1:8002'
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Read-only checks returned HTTP 200 from `http://127.0.0.1:5174/` and the proxied `http://127.0.0.1:5174/api/health/A21`. The served prediction retained model `cmapss-fd001-rf-v1`, RUL `52.286680486180494` cycles, null probability, and `CRITICAL` risk. Port 5173 was not restarted or modified.

From `E:\Projects\Air fleet\frontend`:

```powershell
npm run build
# passed; 57 modules transformed

npm run verify:views
# passed; 19/19 static SSR views rendered

node --test scripts\prediction-contract.test.mjs
# passed; 1/1 test
```

The browser rehearsal on `http://localhost:5174` passed the FD001 prediction/provenance and PM-001 timeline, human-selected HP-204 triage, Commander approval of T-103, Logistics receipt, and Base Manager start/completion of WO-1046. After maintenance, the aircraft remained `AT_RISK` at 52.29 cycles; the UI did not claim telemetry-based recovery.
