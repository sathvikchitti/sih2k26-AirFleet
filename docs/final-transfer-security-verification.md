# Transfer reserve-override security verification

## Scope and policy conclusion

This verification covers reserve override authorization, protected reservations, stock arithmetic, audit behavior, transfer request binding, and recommendation-approval routes. No production behavior change was needed: the exercised API routes enforce their existing demo capability checks and the transfer service enforces the reservation floor independently of the override flag.

The application uses caller-selected demo roles, not authenticated user identities. In hardened mode, `/api/transfers/{transfer_id}/approve` requires `X-Demo-Role: logistics`, whose capability includes `transfers:manage`. A body `actor` or `allow_reserve_override: true` does not grant that permission. The role header takes precedence over a conflicting body actor. These checks are demo authorization behavior, not production authentication.

The Logistics override can reduce unreserved stock below `minimum_reserve`; it cannot spend quantities already reserved for maintenance. A reserve-override audit event is written only when the approved dispatch actually crosses the minimum. At the exact minimum boundary, passing the override flag does not create an override event.

Recommendation approval is a separate Commander-authorized API. Its candidate evaluation excludes sources that violate minimum reserve, so the Commander route's `allow_reserve_override` flag cannot currently select a reserve-infeasible source. The flag does not turn a rejected donor into a candidate. Direct service calls in existing workflow tests exercise the lower-level approval behavior and do not represent HTTP authorization.

## Findings classification

| Finding | Result |
|---|---|
| `allow_reserve_override` grants transfer permission to Base/Commander/missing/invalid roles | **Not reproduced.** Hardened HTTP approval returns 403 before mutation; the flag is not an authorization capability. |
| Logistics is authorized to override minimum reserve | **Confirmed by current capability policy.** Logistics has `MANAGE_TRANSFERS` and `MANAGE_RESERVATIONS`; existing tests explicitly exercise Logistics override. No Commander-only policy was found. |
| Override can consume maintenance-reserved stock | **Not reproduced.** Approval rejects quantities exceeding `quantity - reserved`, even with override enabled; full repository snapshots remain unchanged on denial. |
| Override event can misstate an unneeded override | **Not reproduced.** It is emitted only when `quantity - transfer_quantity - reserved < minimum_reserve`. An exact-boundary transfer with the flag set has no override event. |
| Recommendation override selects an infeasible reserve donor | **Current behavior limitation, not an authorization defect.** Recommendation selection only operates on feasible candidates; a Commander request with the flag set still fails when all donors violate reserve. No state changes occur. |
| External identity authentication | **Not provided by this demo.** The hardened role header is a caller-selected role label, not an authenticated principal. This is a deployment boundary, not a bypass of the demo capability checks. |

No donor-source ownership restriction is defined by the current transfer policy: a Base Manager may request an inbound transfer to their selected base, while Logistics approves and dispatches. When a work-order ID is supplied, transfer creation validates the part, destination, and optional aircraft against that work order. `for_aircraft` without a work-order link is display metadata and is not independently validated against aircraft/base ownership.

## Transfer creation and approval path

`POST /api/transfers` (`backend/app/routers/transfers.py:30-56`) resolves the caller's selected role using `REQUEST_RESOURCE` or `MANAGE_TRANSFERS`, and applies the Base Manager's destination-base scope. It then calls `transfer_service.create_transfer` (`backend/app/services/transfer_service.py:38-83`), which rejects same-base/unknown-base routes, unknown catalog parts, and invalid linked-work-order part/destination/aircraft relationships before creating a pending transfer. With a `work_order_id`, the WO must exist, require the same component, target the destination base, and match the optional `for_aircraft`; an active transfer for that WO is also rejected.

The new pending transfer is stored through `TransferRepository.create` (`backend/app/repositories/transfer_repository.py:44-49`) and the successful request gets a `TRANSFER_CREATED` audit record. Creating a pending transfer does not debit stock. Approval at `/api/transfers/{transfer_id}/approve` checks Logistics permission before calling the service. `approve_transfer` (`backend/app/services/transfer_service.py:91-148`) loads the linked transfer and current inventory line, checks current pooled condition, and verifies `quantity <= inventory.quantity - reserved` before considering minimum reserve. Only after all checks does it update quantity and mark the transfer in transit. Those sequential in-memory writes run under the shared state lock. Tests compare full state snapshots across denied requests and verify the actual inventory result for successful overrides.

## Evidence

- `backend/app/routers/transfers.py:61-78` resolves the selected demo role against `Permission.MANAGE_TRANSFERS` before passing the override flag to the service.
- `backend/app/routers/recommendations.py:47-70,96-114` requires `Permission.APPROVE_RECOMMENDATION` for the Commander recommendation routes.
- `backend/app/domain/enums.py:157-176` defines the role capabilities: Logistics has transfer and reservation management; Commander has recommendation approval; Base has resource request.
- `backend/app/services/transfer_service.py:123-151` checks physical unreserved quantity first, then the post-dispatch minimum. Only the latter check is overridable, and the audit event is emitted only when the minimum is crossed.
- `backend/app/services/transfer_service.py:250-289` selects the already feasible recommendation candidate before creating and approving a transfer. The route's flag therefore does not turn a rejected donor into a candidate.
- `backend/app/services/audit_service.py:176-180` records the override event with the resolved actor and donor base. The event is associated with the work order when present, otherwise the transfer.
- `backend/tests/test_inventory_hardening.py:55-76` covers a lower-level Logistics override and that a reserved unit remains protected.
- `backend/tests/test_workflow.py:361-374` covers a lower-level Commander workflow override example. It invokes the service directly; HTTP route permissions remain separately enforced.
- `backend/tests/test_reserve_override_authorization.py` adds API regressions for role checks, header precedence, reserve-breach atomicity, maintenance-reserved stock, exact-boundary audit behavior, and Commander recommendation feasibility.
- `backend/tests/test_transfer_authorization.py` covers cross-base inbound request scope, valid and invalid role/base claims, body/query actor escalation, and work-order/component/destination/aircraft relationship checks.

Audit detail limitation: `RESERVE_OVERRIDE_APPLIED` records actor and donor base, but does not include the transfer ID when associated with a work order, nor before/after stock quantities. This is a traceability enhancement opportunity, not an authorization bypass or stock-integrity defect.

Other transfer-integrity limitations noted during review but not changed here: transfer condition is evaluated against the inventory line's pooled condition rather than per-unit identity, and the no-work-order `for_aircraft` field is not a binding relationship. The system has no per-unit stock provenance model; these issues require a separate inventory/transfer integrity scope.

The transfer condition is captured when a pending transfer is created, while approval rechecks the current pooled inventory-line condition and dispatch carries the captured transfer condition to receipt. A pending work order's status is not revalidated as a separate eligibility gate by direct transfer approval. These are workflow/inventory integrity limitations outside this reserve-authorization check, not observed role bypasses.

## Verification commands and results

From `E:\Projects\Air fleet\backend`:

```powershell
python -m pytest tests/test_reserve_override_authorization.py -q
python -m pytest tests/test_reserve_override_authorization.py tests/test_transfer_authorization.py tests/test_inventory_hardening.py -q
python -m pytest -q
python -m tests.test_workflow
```

Results:

- Focused reserve-override suite: **11 passed**.
- Combined reserve, transfer-authorization, and inventory-hardening suites: **29 passed**.
- Full backend pytest suite: **164 passed** (28.78 seconds).
- Workflow regression script: **103 passed, 0 failed**.

The FastAPI TestClient pytest commands were run with approved elevated execution because sandboxed Windows socket access can hang the local ASGI test client. The workflow script was also run elevated; it completed all 103 checks.

The production model artifact was not modified or retrained. SHA-256 observed before and after this verification: `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9` (`backend/models/cmapss_fd001_rf_v1.joblib`).

Files changed for this verification: `backend/tests/test_reserve_override_authorization.py` (new API/stock-integrity regressions), `backend/tests/test_transfer_authorization.py` (tightened transfer relationship assertions), and this report. No production code, model artifact, runtime process, or demo state was changed.

API compatibility contracts and production routes were not changed.

## Frontend verification

From `E:\Projects\Air fleet\frontend`:

```powershell
npm run verify:views
npm run build
node --test scripts/prediction-contract.test.mjs
```

Results reported for this verification: view checks **19/19 passed**; Vite 6.4.4 production build **passed** (53 modules); prediction contract test **1/1 passed**. The `postcss-selector-parser` override remains pinned at `7.1.6`. No frontend API compatibility contract was changed for this reserve-override task.

## Remaining policy boundary

Read endpoints remain unauthenticated and lack enforced read authorization. This is an unresolved deployment limitation; this verification does not establish production readiness or security compliance.

`DEMO_PERMISSION_MODE=hardened` enforces the selected role's capability, but the role selector is still a demo claim and is not identity authentication. A production deployment must replace it with trusted principal authentication and server-derived role assignment. The current Commander recommendation path also cannot override an infeasible reserve source; extending that workflow would require an explicit policy and UX decision rather than interpreting the boolean as extra authority.
