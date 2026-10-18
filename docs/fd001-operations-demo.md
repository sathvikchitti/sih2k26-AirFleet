# FD001 synthetic fleet operations demo

This opt-in scenario layers synthetic operational records over the existing trained FD001 model and its fixed NASA C-MAPSS test-engine histories. It does not generate new sensor trajectories, retrain the model, or modify the model artifact. The operational layer keeps the existing 10 aircraft, 3 bases, 4 catalogued parts, and in-memory repositories.

## Start and reset

From `backend/` start the app with both explicit settings:

```powershell
$env:ML_PROVIDER = 'fd001'
$env:DEMO_SCENARIO = 'fd001_operations'
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal, start the existing frontend:

```powershell
cd frontend
npm run dev
```

To inspect fixture links, call `GET /api/demo/scenario`. It returns the stable scenario ID and aircraft, event, work-order, and transfer references; operational values still come from the regular fleet, aircraft, inventory, maintenance, transfer, and recommendation APIs. Work orders expose `component_source` (`human_selected` for predictive-event triage, `fixture_scenario` for the other manually configured tasks). Model predictions retain their own FD001 provenance and never receive the selected component.

Restore the same state with a Commander demo-role claim:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/demo/reset `
  -Headers @{ 'X-Demo-Role' = 'commander' }
```

Reset rebuilds the complete in-memory scenario from the same IDs and operational choices. Runtime timestamps and timestamp-based prediction-history IDs change, and Random Forest RUL values may differ by floating-point noise below 1e-8; aircraft/work-order/event/transfer relationships, statuses, reserve rules, stock totals and displayed model values remain equivalent. To return to the clean FD001 state, stop the app, remove `DEMO_SCENARIO` from the environment, and restart; the default provider remains mock when `ML_PROVIDER` is unset. Selecting this scenario with mock or an unsupported scenario name fails startup instead of silently falling back.

The existing [clean FD001 readiness walkthrough](fd001-demo-readiness.ps1) assumes there are no operational fixture work orders. Do not run it against this operations scenario. The following PowerShell sequence uses IDs from the manifest and completes case C through the real receive and maintenance routes:

```powershell
$baseUrl = 'http://127.0.0.1:8000'
$scenario = Invoke-RestMethod "$baseUrl/api/demo/scenario"
$caseC = $scenario.scenarios | Where-Object id -eq 'C'

Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/api/transfers/$($caseC.transfer_id)/receive?actor=logistics" `
  -Headers @{ 'X-Demo-Role' = 'logistics' }

$baseHeaders = @{ 'X-Demo-Role' = 'base'; 'X-Demo-Base' = 'Alpha' }
Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/api/maintenance/work-orders/$($caseC.work_order_id)/start?actor=base" `
  -Headers $baseHeaders
Invoke-RestMethod -Method Post `
  -Uri "$baseUrl/api/maintenance/work-orders/$($caseC.work_order_id)/complete?actor=base" `
  -Headers $baseHeaders

Invoke-RestMethod "$baseUrl/api/fleet"
```

Case B is a separate manual approval flow: approve its evaluated recommendation as Commander, then receive the returned transfer as Logistics; a Base Manager scoped to Charlie can start and complete its work order after receipt. Case C already has an IN_TRANSIT transfer and must not be approved again. Case E is already IN_PROGRESS and can be completed by a Base Manager scoped to Bravo. Approval, receipt, and maintenance actions are manual API calls; they are not automatic UI transitions.

## Inspecting a cycle-based spares forecast

The default UI forecast horizon is 60 cycles. At this horizon, the alternating demo map plus this fixture's stock and reserve state produced two eligible predictions and seven outside the horizon. The preview proposed one feasible HP-204 unit from Charlie to Bravo (260 km, estimated 4.3 hours). Bravo had expected HP-204 demand 0.1781 and one unit at its minimum reserve; Charlie's HP-204 source had one transferable unit before the proposal. The preview debits that unit only in its cloned suggestion ledger. Charlie's OE-310 demand was 0.4215 with three units at a minimum reserve of three, so it had no transferable OE-310 stock. The endpoint is read-only: viewing a suggested move does not reserve inventory or create a transfer.

In the UI, select Logistics and use the forecast panel's request action on a feasible suggested move. This submits a separate pending transfer request through the existing API. The equivalent request is:

```powershell
$headers = @{ 'X-Demo-Role' = 'logistics' }
$body = @{
  part_number = 'HP-204'
  source_base = 'Charlie'
  dest_base = 'Bravo'
  quantity = 1
  actor = 'logistics'
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/transfers' `
  -Headers $headers -ContentType 'application/json' -Body $body
```

`POST /api/transfers` returns a `PENDING_APPROVAL` transfer. It does not approve, dispatch, receive, or reserve stock. Those are separate role-checked actions, and the live approval path checks current inventory again. Treat the body above as an example only; use a move the current forecast marks feasible, because state and forecast values may change. Demo-role headers are caller-selected claims, not authenticated identities.

## Six scenario cases

| Case | Aircraft | Fixture state | What to inspect |
|---|---|---|---|
| A — Normal operations | A17 | FD001 engine 1 returns LOW risk; no active work order | Aircraft and fleet endpoints show model-derived status, with no operational task attached. |
| B — Predictive maintenance | A32 | FD001 engine 8 returns HIGH risk; open prediction event and human-selected FP-102 work order | `GET /api/work-orders/{id}/recommendation` shows a feasible remote option. It is an evaluation only; no transfer has been approved. |
| C — Cross-base shortage | A21 | FD001 engine 3 returns CRITICAL risk; human-selected HP-204 work order; Commander-approved Charlie transfer is already IN_TRANSIT to Alpha | Inventory/search shows Bravo's one HP-204 protected at reserve and Charlie as the feasible donor. The next workflow action is Logistics receipt of the listed transfer. |
| D — No feasible transfer | A28 | Synthetic manual OE-310 inspection at Bravo; Alpha and Charlie quantities are entirely protected by minimum reserve | Recommendation has no feasible candidate and reports `MINIMUM_RESERVE_VIOLATION` for both donors. No transfer is created. |
| E — Maintenance in progress | A26 | Synthetic manual FP-102 task is IN_PROGRESS; Bravo's one unit is reserved against this work order | Work order and inventory views show the live reservation and the aircraft counted under maintenance. A Base Manager may complete the task. |
| F — Completed maintenance | A24 | Synthetic manual AV-077 task used a real Alpha-to-Bravo transfer, receipt, reservation and consumption; work order is COMPLETED | Transfer history is RECEIVED, the received unit is consumed, and current stock and fleet state reflect the workflow. A24 remains DEGRADED because its mapped FD001 history still predicts MEDIUM risk. |

The fixture uses explicit demo-role permissions before invoking existing services. C's initial transfer is already in transit; do not create a second approval. For manual requests on a Base Manager's aircraft, the service uses that aircraft's existing base assignment. The role headers represent caller-selected demo claims and are not production authentication.

## Data and accounting notes

The provider continues to map the existing ten aircraft IDs to FD001 test engines 1–10. The default demo engine-to-part map assigns odd engines to HP-204 and even engines to OE-310; it is configurable and synthetic. The locally trained model artifact produced A17/engine 1 at 123.9902 cycles (LOW), A21/engine 3 at 52.2867 cycles (CRITICAL), A24/engine 5 at 85.9682 cycles (MEDIUM), and A32/engine 8 at 65.4386 cycles (HIGH). These are model outputs from fixed simulated test histories, not fixture-assigned RUL values. All model outputs retain `rul_unit: cycles`, `failure_probability: null`, `subsystem: null`, `is_synthetic: true`, and the existing model version. No cycle-to-hour/calendar conversion is introduced. Health and risk are the existing derived display indicators, not calibrated probability.

The fixture's aircraft/base assignments, work-order labels, reserve policies and task progress are synthetic operational context. Predictive-event triage choices are marked `component_source: human_selected`; they are not predictions by the FD001 model. This small catalog has no aircraft-specific compatibility or airworthiness data. The choices use catalogued components and existing resource conditions but do not assert engineering fit.

Before any scenario movement, the initializer normalizes Alpha FP-102's inherited mock reservation to zero because its original mock work order is absent in clean FD001 state. It then configures initial donor reserves: Bravo's one HP-204 stays at reserve; Alpha's two and Charlie's three OE-310 units stay at reserve. These are fixture starting rules. All subsequent quantity movements use the existing approval, receive, maintenance start, and completion services. The resulting state has five work orders and two transfers; only A26's in-progress FP-102 remains reserved. C dispatches one HP-204 from Charlie and leaves its remaining unit transferable. F sends one AV-077 from Alpha, receives it at Bravo, reserves it for maintenance, and consumes it on completion. No quantity is changed by rejection or by candidate evaluation.

Fleet metrics are computed by the existing availability service from aircraft/work-order state. The fixed FD001 histories do not advance after repair, so maintenance completion does not imply recovery or change the next prediction. This is an illustrative local demo, not real aircraft telemetry, operational integration, or validation of readiness decisions.
