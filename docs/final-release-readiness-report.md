# Final release-readiness verification

This report records the final transfer, reserve-override audit, readiness-planning, and frontend verification work. It is a synthetic POC verification, not operational or airworthiness certification.

## What changed

| File | Purpose |
|---|---|
| `backend/app/services/audit_service.py` | Adds an auditable reserve-override context, including actor role, transfer/inventory references, source and destination, before/after quantities, reserved and minimum-reserve quantities, floor crossing, and resulting status. The event is written only after the authorized dispatch succeeds. |
| `backend/app/services/transfer_service.py` | Revalidates linked work-order/component/base relationships and source stock/condition at dispatch; records the dispatch-time condition; applies conservative pooled condition on receipt; does not mark stale or unusable linked work orders serviceable. |
| `backend/app/services/planning_service.py` | Projects in-transit arrival against receipt condition, available stock, and the linked work order’s part, destination, and optional aircraft. A stale/mismatched transfer is marked `can_start_on_arrival: false` with `TRANSFER_WORK_ORDER_MISMATCH`. |
| `backend/app/services/readiness_service.py` | Does not project repair start/completion for an in-transit allocation that cannot satisfy maintenance-start constraints on arrival. |
| `backend/tests/test_reserve_override_audit_context.py` | Verifies reserve-override audit fields and their before/after values. |
| `backend/tests/test_recommendation_override_policy.py` | Verifies alternate feasible candidates remain selectable and infeasible/reserve-blocked candidates remain rejected without writes. |
| `backend/tests/test_transit_readiness_feasibility.py` | Verifies receipt eligibility and stale transfer/work-order links do not produce simulated completion. |
| `backend/tests/test_transfer_revalidation.py` | Verifies dispatch and receipt revalidation, stale work orders, reserve/condition changes, and mixed-grade receipts. |
| `README.md` | Documents the difference between Commander candidate choice and Logistics reserve override, pooled-condition behavior, and readiness projection constraints. |
| `frontend/src/components/ReadinessSimulationPanel.jsx` | Avoids declaring a policy tie when time-weighted availability is unavailable, including a zero-hour horizon. |
| `frontend/src/pages/views/InventoryView.jsx` | Shows when an in-transit arrival will still be unusable for its linked work order. |
| `frontend/scripts/render-check/entry.jsx` | Adds SSR checks for unavailable comparison values and arrival-serviceability messaging. |

No production model artifact, training data, active pre-existing demo runtime, or dependency manifest was changed for this release-readiness task. The isolated mock compatibility process on 8010 ran its intended stateful test/reset and was stopped; the isolated FD001 process on 8009 is reserved for the authorized rehearsal. No existing tests were weakened. `test_reserve_override_authorization.py` is an existing regression file from the prior hardening task and was verified by the final suite; it was not changed in this pass.

## Policy and integrity findings

Direct transfer approval requires the Logistics capability. An explicit reserve override can cross the configured minimum reserve, but never consumes reserved stock. The override is recorded with the actual stock and transfer state after a successful dispatch. A Base Manager or Commander role claim cannot gain Logistics transfer authority by setting the override flag.

Commander recommendation approval can select a different feasible donor. It does not bypass candidate feasibility: stock, reserve, catalog condition, and other hard checks still apply. The API’s `allow_reserve_override` flag does not make an infeasible recommendation candidate selectable. This is a documented capability boundary, not a Commander-only override policy.

At receipt, a non-empty pooled inventory line keeps the lower of its current condition and the incoming condition; an empty line takes the incoming condition. This avoids upgrading existing lower-grade units when per-unit/lot condition is unavailable. It can understate better incoming units. The readiness planner uses the same conservative rule and checks transferable quantity and minimum condition before counting an arrival as enabling maintenance. It also rejects stale links where the dispatched component, destination, or optional aircraft differs from the current work order. Multiple unreceived arrivals are not netted together in the projection.

The in-memory demo’s role and base headers are caller-selected claims, not authenticated identities. Read routes are not authenticated. Reserve-override records are in-memory audit entries, not append-only durable evidence; reset and restart can replace them. The project therefore remains a prototype and is **not certified for defense or operational deployment**; it needs identity-backed authorization, durable transactional storage, and operational engineering validation before production use.

| Finding | Result |
|---|---|
| Stale transfer/work-order links could make a readiness plan project a repair that cannot start | Fixed: the planner blocks projection for mismatched part, destination, or optional aircraft; regression tests cover each case. |
| Mixed-grade receipt could upgrade existing pooled stock and falsely make maintenance startable | Fixed conservatively: pooled condition uses the lower grade; receipt and planning enforce the same availability and condition floor. |
| Dispatch could use a stale pending-transfer work-order link or stale source-condition snapshot | Fixed: dispatch revalidates linkage, work-order eligibility, current source quantity/reserve/condition and stores the actual dispatch condition before the transfer becomes in transit. |
| A reserve override could be hard to audit after stock was moved | Fixed: successful floor-crossing decisions carry the additive context listed above; failed dispatches do not write a successful override record. |
| Reserve override audit omitted enough context to verify the stock decision | Fixed: successful crossing records the actor, inventory/transfer identities, before/after quantities, reserve values, crossing, and resulting status. |
| Commander alternate choice could bypass feasibility | Verified restricted: only feasible candidate choices are available; the override flag does not bypass hard constraints. |
| Logistics reserve override authorization and reserved-unit protection | Verified: unauthorized roles and protected reserved quantities are rejected atomically; authorized Logistics override behavior remains supported. |
| Zero-horizon simulator could present unavailable values as a policy tie | Fixed: the UI reports that the policies cannot be compared when time-weighted values are unavailable. |
| In-transit receipt may still be unusable under the destination reserve or pooled condition | Fixed: plan response includes `can_start_on_arrival` and `arrival_block_reason`; the UI warns and the readiness projection does not claim a completion. |
| API compatibility after final hardening | Verified: the legacy compatibility harness passes. A newly stale transfer/work-order request is rejected with HTTP 400 and its existing `detail` response shape; successful payloads retain existing response keys with additive audit/planning fields. |
| Authenticated identities, authenticated read routes, durable append-only audit history, per-unit condition provenance, multi-arrival netting, and deployment certification | Unresolved/accepted prototype limits; no new auth or lot-tracking architecture was introduced. |
| Existing scheduled/resource-available states with no active reservation | Existing lifecycle policy is preserved; this work did not invent a stricter resource-state rule. A received transfer linked to a closed or relinked work order still credits physical destination stock but does not advance that work order. |
| Frontend dependency advisories | See [the dependency remediation note](dependency-remediation.md). This task made no dependency changes and did not claim a fresh advisory scan. |

The stale-link, dispatch-condition, mixed-grade, audit-context, simulator, and UI fixes are covered in the listed backend/frontend checks. The existing reserve-override authorization regressions were also included in the final suite but were not modified in this pass.

## Verification

The local FD001 model artifact hash before and after this work was:

```text
SHA256 14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9
```

The artifact was not retrained or overwritten. The initial baseline was 164 backend tests and 103 workflow checks; final verification after the transfer and planning updates was:

| Check | Command and directory | Result |
|---|---|---|
| Focused readiness and in-transit serviceability | `python -m pytest tests/test_transit_readiness_feasibility.py tests/test_readiness_simulator.py -q` from `backend/` | 14 passed |
| Final focused transfer/reserve/readiness gate | `python -m pytest tests/test_transfer_revalidation.py tests/test_inventory_hardening.py tests/test_recommendation_override_policy.py tests/test_reserve_override_audit_context.py tests/test_transit_readiness_feasibility.py -q` from `backend/` | 48 passed in 0.64s |
| Full backend suite | `python -m pytest -q` from `backend/` | 207 passed in 29.31s |
| End-to-end workflow | `python -m tests.test_workflow` from `backend/` | 103 passed, 0 failed |
| Legacy API compatibility | `python -c "import tests.test_api_compat as t; t.BASE='http://127.0.0.1:8010'; assert t.main.__globals__['BASE']=='http://127.0.0.1:8010'; print('compat BASE:', t.main.__globals__['BASE']); raise SystemExit(t.main())"` from `backend/`, against an isolated mock server | 61 passed, 0 failed |
| Frontend view verification | `npm run verify:views` from `frontend/` | 19/19 views; readiness comparison and arrival-state SSR assertions passed (4 comparison cases, 3 arrival cases) |
| Frontend production build | `npm run build` from `frontend/` | Passed, Vite 6.4.4, 53 modules |
| Prediction contract | `node --test scripts/prediction-contract.test.mjs` from `frontend/` | 1 passed |

The initial sandboxed full-suite command stalled after 12 tests, so that test process was stopped and the same command was run with the approved elevated execution path; it completed successfully. The workflow command completed successfully with the approved elevated execution path as well. The API compatibility harness was explicitly pointed to port 8010 by assigning its module-level `BASE` and asserting the function’s actual globals before execution; it did not target the existing demo server. The exact focused group above was then rerun and passed after the final planner-link regression was added.

## Isolated FD001 runtime

For browser verification, the final backend was started on `127.0.0.1:8009` (PID 10232) with `ML_PROVIDER=fd001`, `DEMO_PERMISSION_MODE=hardened`, `DEMO_RESET_ENABLED=false`, `DEMO_SCENARIO` unset, and CORS origins for `http://localhost:5177` and `http://127.0.0.1:5177`. This is an isolated server; existing demo ports were left untouched. Initial read-only checks returned health 42, RUL 52.286680486 cycles, `failure_probability: null`, model `cmapss-fd001-rf-v1`, synthetic FD001 test-history provenance, and zero work orders on the aircraft timeline. The isolated mock compatibility server on port 8010 was stopped after its test run.

The authorized browser rehearsal on `http://localhost:5177` used the isolated FD001 backend. The operator triaged A21's synthetic FD001 event PM-001 by selecting HP-204, creating WO-1046 with `component_source: human_selected`, a 52.2867-cycle RUL, `rul_unit: cycles`, and no flight-hour deadline. Commander selected feasible donor Bravo (42% condition against a 40% minimum; ETA 2h, 120km; Charlie remained the alternate at 84%, 6.3h), approved transfer T-103, and Logistics received it at Alpha. Base Alpha then started and completed WO-1046. The UI showed the HP-204 arrival as one earmarked unit with zero transferable units before maintenance; afterward Alpha and Bravo each had quantity/reserved 0/0 and Charlie had 2/0. PM-001 resolved, WO-1046 completed, T-103 received, and A21 remained AT_RISK at 52.29 cycles because the fixed simulated history does not provide post-repair telemetry. No model-confirmed recovery is claimed.

The case timeline retained one event, one work order, one recommendation snapshot, one approval decision, and one transfer. It showed distinct audit transitions for transfer dispatch/receipt, resource availability, maintenance start, progress, and completion. Repeated timeline refreshes did not duplicate evidence. A read-only verification after the UI flow confirmed 23 audit events before and after repeated timeline/audit GETs. Fleet availability was 6/10. The 48-hour simulator showed 60% time-weighted availability for all three policies; completed-work-order counts were 0/1/1 for no new allocation, nearest-feasible, and proposed. The tie is an observed result for this snapshot, not a performance claim. At a zero-hour horizon the metric is unavailable and the UI says policies cannot be compared on that measure.

The completed WO response still contains `resource_reserved: true`, although the inventory line reservation is 0 and the WO is closed. This is a stale work-order flag retained after completion, not an active inventory reservation; the closed WO is not counted as an active allocation. The transfer record contains a `created` timestamp, but the current timeline projection/UI expects `created_at`, so the transfer time is shown as unavailable. This is a minor display-mapping gap; no timestamp was inferred. The demo reset affordance can remain visible when reset is disabled and then receives HTTP 403; this does not bypass the backend guard. Screenshots from the rehearsal are `release-completion.jpg`, `release-fd001-timeline.jpg`, and `release-zero-horizon.jpg` in the task visualization directory.

## Freeze assessment

The controlled synthetic rehearsal and automated gates are complete with no known critical workflow defect in the exercised paths. This is release-ready only for the isolated SIH demo/prototype scope. It is not a certification for operational defense use. Remaining accepted issues are the stale `resource_reserved` flag on a completed WO, the `created` versus `created_at` timeline display mapping, caller-selected demo identities and unauthenticated reads, and the disabled-reset UI affordance; these do not change the tested stock, authorization, or completion outcomes.

To reproduce the isolated backend configuration from `backend/`:

```powershell
$env:ML_PROVIDER = 'fd001'
$env:DEMO_PERMISSION_MODE = 'hardened'
$env:DEMO_RESET_ENABLED = 'false'
$env:FRONTEND_ORIGINS = 'http://localhost:5177,http://127.0.0.1:5177'
Remove-Item Env:DEMO_SCENARIO -ErrorAction SilentlyContinue
python -m uvicorn app.main:app --host 127.0.0.1 --port 8009
```

The matching development UI was started from `frontend/` with this PowerShell configuration:

```powershell
$env:API_PROXY_TARGET = 'http://127.0.0.1:8009'
Remove-Item Env:VITE_API_BASE -ErrorAction SilentlyContinue
npm run dev -- --host 127.0.0.1 --port 5177 --strictPort
```

It is running at `127.0.0.1:5177` (PID 30908). Direct and proxied audit responses were byte-identical before the browser rehearsal; the proxied A21 health response matched the direct FD001 provider fields. If either port is occupied for a future reproduction, choose a fresh unused backend/frontend port pair and update `FRONTEND_ORIGINS` and `API_PROXY_TARGET`; do not stop an unowned process. The original demo ports and their state were not reset or used for verification.

Final reviewer HTTP checks returned 200 from both `http://127.0.0.1:8009/api/health` and `http://127.0.0.1:5177/`. These read-only checks required the approved elevated execution path; sandbox socket restrictions were not treated as evidence that either server had stopped.
