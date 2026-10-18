# Read-only planning and case-timeline verification

This note records the shared-stock preview, readiness comparison, and maintenance-case timeline added to the existing in-memory demo. These services make planning evidence available; they do not authorize or perform a proposed allocation. Live approval still rechecks current stock and permissions.

## API additions

- `GET /api/resources/allocation-preview?work_order_ids=WO-...` previews shared allocations for all open work orders, or a selected subset. It returns `allocations` with `allocation_status`, ranked `candidates`, `conflicts`, `inventory_effects`, selected/unknown work-order IDs, and `mutated_state:false`. Existing commitments from non-selected open orders still consume the virtual ledger. The priority/age/ID order is deterministic; pending approvals are provisional, dispatched transfers are already debited, and received/local units are earmarked for their work orders.
- `GET /api/fleet/readiness-simulation?horizon_hours=48&work_order_ids=WO-...` returns the `no_action`, `nearest_feasible`, and `proposed` policies over one frozen snapshot. No-action means no new allocations; all policies share existing in-transit arrivals and ongoing maintenance. Pending approvals do not auto-dispatch. Nearest ranks distance first, then ETA and base; proposed uses the current downtime ranking. The response includes an availability curve, available-aircraft-hours, downtime, completed-order counts, assumptions, and `mutated_state:false`.
- `GET /api/aircraft/{aircraft_id}/maintenance-timeline?work_order_id=WO-...` links prediction history, events, work orders, recorded recommendation evaluations, decisions, transfers, and audit entries through stored identifiers only. The optional work-order filter must belong to the aircraft. The response exposes current record arrays, `timeline`, `linkage`, and `mutated_state:false`. It never runs a new recommendation evaluation. New event-triage work orders record `component_source` (`human_selected` or `knowledge_rule`) on the work order and creation audit. Explicit component choice does not prove aircraft-level compatibility or airworthiness.

Legacy unresolved events can be reused by later ingests. Their original cause remains `prediction_history_origin_status: legacy_unknown`; later observations are listed as linked observations, without claiming they caused the original event. Unlinked legacy prediction audits remain explicitly unlinked. Work-order and transfer timeline rows show their current status snapshot and are timed by their creation timestamp; audit rows represent actual transitions. Stored recommendation snapshots may differ from current inventory.

## Verification

Commands were run from `E:\Projects\Air fleet\backend` unless stated otherwise.

| Check | Baseline | Final |
|---|---|---|
| Backend pytest bundle | 54 passed, including four evaluation tests | `python -m pytest -q --basetemp .pytest-tmp` → 78 passed in 28.90s |
| End-to-end workflow | `python -m tests.test_workflow` → 103 passed | `python -m tests.test_workflow` → 103 passed, 0 failed |
| API compatibility | 61 passed | fresh mock Uvicorn on isolated port 8005; script's actual `main.__globals__['BASE']` asserted as `http://127.0.0.1:8005`, then `main()` → 61 passed, 0 failed |
| Frontend build and SSR | build: 55 modules; `verify:views`: 19/19 | `npm run build`: 57 modules; `npm run verify:views`: 19/19 |

Final focused commands from `backend`: `python -m pytest tests/test_allocation_preview.py -q --basetemp .pytest-tmp` (12 passed), `python -m pytest tests/test_readiness_simulator.py -q --basetemp .pytest-tmp` (7 passed), and `python -m pytest tests/test_maintenance_case.py -q --basetemp .pytest-tmp` (5 passed). These tests are included in the full suite. Windows TestClient suites required elevated execution because the sandbox stalled on local socket tests.

The trained FD001 artifact was not modified or retrained. SHA256 before and after: `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`.

## Read-only runtime smoke

A clean FD001 server was started on `127.0.0.1:8006` with `ML_PROVIDER=fd001`, `DEMO_SCENARIO` unset, and `FRONTEND_ORIGINS=http://127.0.0.1:5174` (final server PID 30728). From PowerShell:

```powershell
Set-Location 'E:\Projects\Air fleet\backend'
$env:ML_PROVIDER = 'fd001'
Remove-Item Env:DEMO_SCENARIO -ErrorAction SilentlyContinue
$env:FRONTEND_ORIGINS = 'http://127.0.0.1:5174'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8006
```

The isolated frontend command was `Set-Location 'E:\Projects\Air fleet\frontend'; $env:VITE_API_BASE='http://127.0.0.1:8006'; npm run dev -- --host 127.0.0.1 --port 5174 --strictPort`. The A21 health request returned 200 with model `cmapss-fd001-rf-v1`, RUL `52.286680486180494` cycles, `failure_probability:null`, `subsystem:null`, and `is_synthetic:true`. A21 had event PM-001 and no work orders on clean startup. Timeline, allocation preview, and readiness simulation returned 200 and reported `mutated_state:false`; readiness returned all three policies. CORS preflight allowed origin `http://127.0.0.1:5174`.

Two distinct FD001 scenarios were checked. In the opt-in operations fixture (ten mapped simulated histories), readiness was 40% at the snapshot and 50% at the horizon under all three policies; time-weighted availability was 49.375% for each. No-action completed two work orders; nearest and proposed completed three each. The policies tied on availability, so no superiority claim is supported. In the clean FD001 UI scenario, readiness was 60% both at the snapshot and horizon. After the browser maintenance flow, the fleet remained 6/10 available (60%) and A21 remained AT_RISK because static FD001 histories do not advance to post-maintenance telemetry. RUL remains in cycles and is never treated as elapsed hours. The simulator assumes immediate approval of proposed transfers and a full repair duration remaining at snapshot time; it has no crew or maintenance-capacity constraints.

The final browser rehearsal on the isolated `8006` backend and `5174` frontend completed the A21/PM-001 path: Base Alpha explicitly selected HP-204, Commander approved Bravo stock at 42% condition (catalog minimum 40%), Logistics received it, and Base Manager started and completed WO-1046. The UI showed a received-resource earmark of 1 planned claim and 0 transferable before maintenance. Read-only API verification confirmed WO-1046 (`COMPLETED`, `component_source=human_selected`, `required_by_flight_hours:null`, `required_by_rul=52.28668048618049`, `rul_unit=cycles`) and transfer T-103 (`RECEIVED`, Bravo→Alpha, linked to WO-1046). HP-204 ended at quantity/reserved 0 at both Alpha and Bravo. The timeline links PM-001, WO-1046 and T-103, records Commander approval, and shows the corrected transitions `WAITING_FOR_RESOURCE→RESOURCE_AVAILABLE` (Logistics), `RESOURCE_AVAILABLE→IN_PROGRESS` (Base), and `IN_PROGRESS→COMPLETED` (Base). The Commander what-if displayed 60% and 288 available-aircraft-hours over 48 hours, with 0, 1, and 1 completed work orders under no-action, nearest, and proposed respectively. The final API snapshot after maintenance was 6/10 available (60%) with A21 still AT_RISK. This is consistent with fixed FD001 telemetry; no recovery from model risk is claimed. The isolated server remains running as PID 30728. Transfer rows do not contain `created_at`, so their timeline time is left unavailable instead of inferred.

The standalone mock API compatibility harness was first invoked with a `runpy` namespace override that did not change the function's actual `BASE`; it therefore sent its initial reset request to the already-running port 8000. A read-only audit query confirmed `DEMO_RESET` AE-0013 at `2026-10-17T18:33:17.839738+05:30`. The prior in-memory state is unknown, so no restore was attempted. All subsequent compatibility and runtime checks used isolated ports; no further writes were made to 8000. The pre-existing port 8000 and 5173 processes were not stopped.

Interactive browser validation is complete; the view screenshots are stored in the task visualizations folder as `maintenance-completion-final.jpg` and `maintenance-case-final.jpg`. The final FD001 runtime is still available at `http://127.0.0.1:8006` with the completed WO-1046/T-103 demo state; the associated frontend tab remains on `http://127.0.0.1:5174`.

## Changed files

- Backend: `app/services/resource_service.py`, `recommendation_service.py`, `planning_service.py`, `maintenance_service.py`, `transfer_service.py`, `availability_service.py`, `impact_service.py`, `readiness_service.py`, `case_timeline_service.py`, `audit_service.py`; routers `maintenance.py`, `bases.py`, and `aircraft.py`.
- Backend tests: `test_allocation_preview.py`, `test_readiness_simulator.py`, and `test_maintenance_case.py`.
- Frontend: `src/services/api.js`, `src/pages/views/InventoryView.jsx`, `src/components/ReadinessSimulationPanel.jsx`, `src/pages/Commander.jsx`, `src/components/MaintenanceCasePanel.jsx`, `src/pages/AircraftDetail.jsx`, `src/pages/views/MaintenanceView.jsx`, `src/pages/views/BaseMaintenanceView.jsx`, and `src/App.jsx`.
- Documentation: `README.md` and this verification note.
