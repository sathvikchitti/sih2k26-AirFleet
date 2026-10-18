# Backend hardening verification

This note records validation, mutation-audit, and recommendation-read changes in the hardening pass. It supplements the FD001/model and workflow notes in [implementation-verification.md](implementation-verification.md); the model itself was not retrained or modified.

For the frontend's separate dependency/configuration audit, see [frontend-hardening.md](frontend-hardening.md). Its seven-entry count was the initial audit; the later focused parser remediation is recorded in [dependency-remediation.md](dependency-remediation.md), which reports the current five high package entries, all rooted in one unfixed development-tool advisory.

## Behavior

- Recommendation evaluation is now a pure operation. The work-order and aircraft recommendation GET routes, aircraft detail projection, allocation preview, readiness simulation, and maintenance timeline do not append audit records or mutate repository state. A successful human approval records the evaluated recommendation and approval after the transfer succeeds. Rejection remains an explicit, audited decision and does not move stock.
- Successful inventory PATCH requests record one `INVENTORY_UPDATED` audit event with the selected demo actor and before/after values for changed inventory fields. A no-op update, denied request, or invalid request does not add an audit entry.
- JSON booleans are rejected for `condition_pct` and `estimated_repair_hours`; they are not accepted through Python's bool-as-int/float coercion. NaN and infinities return JSON-serializable HTTP 422 validation responses.
- `DEMO_PERMISSION_MODE=hardened` is the default and requires the caller-selected `X-Demo-Role` header for mutations. The roles are demo claims, not authenticated identities. `compat` retains legacy actor fallback only for genuinely headerless legacy requests. A base-role or base-scope header still activates base scoping and requires a matching `X-Demo-Base`.
- `/api/demo/reset` is disabled unless `DEMO_RESET_ENABLED=true`. Reset intentionally replaces the in-memory demo store and clears the audit history; the audit log is not durable or append-only across a demo reset.
- GET endpoints are not identity-authenticated. This remains a local demo API with caller-selected role claims for mutation gating; do not expose it as production-secure or assume audit/fleet reads are confidential.

## Verification

Commands were run from `E:\Projects\Air fleet\backend` unless stated otherwise.

| Check | Baseline before hardening | Final |
|---|---:|---:|
| Backend pytest | 78 passed | `python -m pytest -q` → 140 passed in 28.64s |
| Workflow script | 103 passed | `python -m tests.test_workflow` → 103 passed, 0 failed |
| API compatibility | 61 passed | isolated mock/compat process on 8008; module-bound BASE asserted before harness → 61 passed, 0 failed |
| Focused gate | — | `python -m pytest tests/test_domain_input_validation.py tests/test_inventory_hardening.py tests/test_readonly_audit.py tests/test_fd001_operations_scenario.py -q` → 42 passed in 27.55s |

The Windows TestClient commands required elevated execution because the sandboxed runs stalled on local socket access. The API compatibility command was executed from `backend` as:

```powershell
python -c "import tests.test_api_compat as t; t.BASE='http://127.0.0.1:8008'; assert t.main.__globals__['BASE']=='http://127.0.0.1:8008'; raise SystemExit(t.main())"
```

The separately isolated compatibility server used `ML_PROVIDER=mock`, `DEMO_PERMISSION_MODE=compat`, and `DEMO_RESET_ENABLED=true`. It was stopped after the test. The trained artifact SHA256 before and after all tests is `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`.

## FD001 runtime

The isolated API is running at `http://127.0.0.1:8007` (PID 4396) with `ML_PROVIDER=fd001`, `DEMO_PERMISSION_MODE=hardened`, `DEMO_RESET_ENABLED=false`, `DEMO_SCENARIO` unset, and `FRONTEND_ORIGINS=http://localhost:5175,http://127.0.0.1:5175`. It was started from PowerShell with:

```powershell
Set-Location 'E:\Projects\Air fleet\backend'
$env:ML_PROVIDER='fd001'
$env:DEMO_PERMISSION_MODE='hardened'
$env:DEMO_RESET_ENABLED='false'
Remove-Item Env:DEMO_SCENARIO -ErrorAction SilentlyContinue
$env:FRONTEND_ORIGINS='http://localhost:5175,http://127.0.0.1:5175'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8007
```

Read-only GET probes returned HTTP 200 for `/api/health/A21`, `/api/aircraft/A21`, and `/api/aircraft/A21/maintenance-timeline`. The clean startup has no work orders. A21 reports model `cmapss-fd001-rf-v1`, RUL `52.286680486180494` cycles, derived health score 42, `failure_probability:null`, `subsystem:null`, `required_component:null`, and `is_synthetic:true`. No cycles-to-hours conversion is made.

The isolated frontend at `http://127.0.0.1:5175` was restarted with `API_PROXY_TARGET=http://127.0.0.1:8007` and `VITE_API_BASE` unset, using `npm run dev -- --host 127.0.0.1 --port 5175 --strictPort` from `E:\Projects\Air fleet\frontend`. The new listener is PID 19708 (npm wrapper PID 14856); only the previous isolated 5175 listener PID 42576 was stopped. Read-only GET `/api/audit` returned 12 rows directly from 8007 and through the 5175 proxy; both response bodies had SHA256 `982544765F31BFDAC5C6425B5EAB0BCCB0604F96697460041EA68840A4A4B906` (the 8002 instance returned 13 rows). This confirms the new frontend proxy reaches 8007. No VITE_API_BASE is needed for this same-origin proxy mode.

Existing runtimes at ports 8000, 8002, 8006, 5173, and 5174 were not stopped or restarted by this verification; any process already bound there may still be serving older code. The temporary compatibility server on 8008 was stopped. The 8007 backend and 5175 frontend remain running with the completed isolated browser walkthrough state.

## Browser workflow and final read-only state

The browser used `http://localhost:5175/`, proxied to the isolated API on 8007. It exercised the actual A21 case: Base Alpha triaged predicted event PM-001 by selecting catalogued HP-204; Commander approved the recommendation from Bravo; Logistics received transfer T-103; Base Manager started and completed WO-1046. The timeline shows PM-001, WO-1046, the stored recommendation, T-103, and the approval/receipt/maintenance transitions with their selected demo actors. Human component selection is recorded as `component_source=human_selected` and on the creation audit; the FD001 prediction itself continues to have no subsystem or component.

Read-only API verification after the browser run returned: PM-001 `RESOLVED`; WO-1046 `COMPLETED`, linked to PM-001, with `required_by_flight_hours:null`, `required_by_rul:52.2866804861805`, and `rul_unit:cycles`; T-103 `RECEIVED`, Bravo→Alpha, linked to WO-1046. HP-204 inventory was Alpha quantity/reserved `0/0`, Bravo `0/0`, Charlie `2/0`. Fleet availability was 6/10 (60%); A21 remains `AT_RISK`, health 42 derived from the model's 52.2867-cycle RUL. That state does not demonstrate post-repair sensor recovery.

Before/after repeated GET checks of `/api/audit` returned 23 rows both times; timeline, fleet, and readiness-simulation reads did not append audit records or alter state. During the browser walkthrough, before WO-1046 was completed, readiness tied at 60% across all three policies and showed 0/1/1 newly completed orders for no-action/nearest/proposed. The final post-completion API probe then showed 60% and 288 available-aircraft-hours for all policies, with 0/0/0 additional completions because the case was already closed. The simulation assumes immediate approval for hypothetical proposed allocations and fixed predictions; it models no crew or maintenance-capacity constraints. Transfer timestamps are displayed from their recorded `created` field; no creation time was inferred where absent.

The browser screenshots are `hardening-fd001-completion.jpg` and `hardening-case-timeline.jpg` in the task visualization folder. The case was refreshed twice and remained one event, one work order, one recommendation decision, and one transfer.

## Files changed in this hardening pass

- `backend/app/security.py`, `main.py`, and routers `aircraft.py`, `inventory.py`, `maintenance.py`, `recommendations.py`, `transfers.py`: hardened mutation permission checks, opt-in reset, inventory validation/audit, and safe 422/503 error responses.
- `backend/app/domain/enums.py`; services `audit_service.py`, `fd001_operations_scenario.py`, `maintenance_service.py`, `recommendation_service.py`, `transfer_service.py`: explicit inventory and recommendation audit writes, pure recommendation evaluation, and validation/transition logic.
- `backend/tests/test_permission_hardening.py`, `test_domain_input_validation.py`, `test_inventory_hardening.py`, `test_fd001_operations_scenario.py`, `test_readonly_audit.py`, `test_fd001_provider.py`, `test_regressions.py`: permission, validation, state immutability, explicit auditing, provider error, and workflow regression coverage.
- Documentation: `README.md`, [implementation-verification.md](implementation-verification.md), [frontend-hardening.md](frontend-hardening.md), and this note.

The API compatibility response shapes remain covered by the isolated 61-check harness. The demo role selector is authorization gating for a local demo only; it does not authenticate users or provide production security.
