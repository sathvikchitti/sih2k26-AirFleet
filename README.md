# Aircraft Fleet Readiness & Sustainment Platform

A deterministic proof of concept for connecting aircraft condition predictions to maintenance planning, resource search, transfer execution, and fleet availability. The recommendation engine is decision support: a human must approve a recommendation before a transfer starts.

## Run the application

The backend uses FastAPI and in-memory repositories. The frontend uses React and Vite.

```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies API calls to port 8000. `FRONTEND_ORIGINS` optionally configures the comma-separated list of allowed browser origins; the default allows `http://localhost:5173` and `http://127.0.0.1:5173`. Credentialed CORS is disabled.

The Commander can restore the deterministic seed through **Reset demo** or `POST /api/demo/reset`. Reset is intended for demonstrations and development, not shared production use.

## Verification

From `backend/`:

```powershell
python -m tests.test_workflow
python -m pytest tests/test_fd001_model.py tests/test_fd001_provider.py tests/test_regressions.py tests/test_recommendation_evaluation.py -q
python -m app.evaluation.recommendation_baseline
```

The legacy API compatibility script expects the backend to be running at `http://127.0.0.1:8000`. It uses headerless legacy mutations, so start that test server with `DEMO_PERMISSION_MODE=compat` and `DEMO_RESET_ENABLED=true`; production-like verification should leave hardened mode enabled and use the permission regression suite instead:

```powershell
python tests/test_api_compat.py
```

From `frontend/`:

```powershell
npm run build
npm run verify:views
```

The frontend view check was a static render/build check only; it did not exercise effects, clicks, mutations, or a live API. The frontend build verifies production bundling.

## Operational workflow

```text
validated prediction
  → predicted maintenance event
  → human triage and work order
  → feasible resource search and ranked alternatives
  → human recommendation approval
  → transfer (pending → in transit → received)
  → maintenance start and component reservation
  → maintenance completion and component consumption
  → aircraft state and fleet availability recalculated
```

A prediction creates or updates a predicted maintenance event; it does not approve or complete maintenance. A work order is created only through explicit triage. A transfer recommendation does not move stock until the Commander approves it. Transfer receipt makes the resource available, and maintenance must start before it can be completed.

## Prediction providers and contract

`backend/app/services/ml/base.py` defines the provider boundary. `ML_PROVIDER=mock` is the deterministic development default. `ML_PROVIDER=fd001` explicitly selects the trained Random Forest integration; a missing/corrupt artifact or missing dataset raises an unavailable prediction and never falls back to mock. The legacy `timestamp` and `rul` fields remain available; normalized results also expose `prediction_timestamp`, `remaining_useful_life`, `rul_unit`, `probability_status`, and prediction provenance. For FD001, RUL is measured in cycles, `prediction_horizon_hours` and `failure_probability` are null/unavailable, and no flight-hour deadline is inferred. A missing subsystem is expected: this model predicts engine RUL only, never aircraft subsystem or component part number. A human must identify the subsystem/component during triage before the existing maintenance workflow can proceed.

The backend validates aircraft identity, timezone-aware ISO timestamps, score/probability bounds, horizon, RUL unit, confidence, and model version before using a prediction. Predictions older than 24 hours or more than five minutes in the future are unavailable. The provider call has a five-second response timeout through a bounded four-worker pool. Python cannot forcibly stop a provider function already running in a worker; a permanently stuck provider can occupy a worker, so the real integration must also enforce its own network/client timeout. Invalid, stale, or unavailable predictions return HTTP 503 with `prediction_status: "unavailable"`; the API does not invent replacement values.

Risk is calculated by the backend, and a model-supplied risk label is ignored. Health thresholds are `<45 CRITICAL`, `<60 HIGH`, `<80 MEDIUM`, otherwise `LOW`. Probability thresholds are `>=0.70 CRITICAL`, `>=0.45 HIGH`, `>=0.25 MEDIUM`, otherwise `LOW`. When signals disagree, the more severe band wins. In mock mode, A17's health score of 41 and failure probability of 0.78 produce `CRITICAL`.

The mock provider emits synthetic, deterministic demo values and identifies its version as `mock-demo-v1`. `prediction_history` contains illustrative seed rows and timestamped provider results; provider-generated mock rows remain marked `is_synthetic: true`. Mock trends are labeled illustrative. FD001 trends are retrospective model inferences over prefixes of simulated engine histories, not observed health telemetry; those histories also carry `is_synthetic: true`. Actual aircraft sensor streams and maintenance outcomes are not available.

## NASA C-MAPSS FD001 model

The local model path uses the official NASA Ames Prognostics Center of Excellence C-MAPSS simulated turbofan data. The canonical [Data.gov dataset record](https://catalog.data.gov/dataset/cmapss-jet-engine-simulated-data) links NASA's [CMAPSSData.zip](https://data.nasa.gov/docs/legacy/CMAPSSData.zip); the NASA [PCoE data repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) describes the turbofan degradation simulation. Place the extracted `train_FD001.txt`, `test_FD001.txt`, and `RUL_FD001.txt` files in repository-root `CMAPSSData/`. The current local copies contain 100 engine train series, 100 test series, and 100 official final RUL labels. The local copies are not accompanied by a signed checksum manifest, so their exact chain of custody cannot be independently verified; the training report records the training file hash for reproducibility.

Install backend dependencies (`numpy`, `scikit-learn`, and `joblib` are pinned in `backend/requirements.txt`) and train from `backend/`:

```powershell
python -m app.services.ml.train_fd001 --metrics models/cmapss_fd001_rf_v1_metrics.json
```

The script fits a 200-tree Random Forest to run-to-failure training RUL targets capped at 125 cycles. It creates a deterministic engine-grouped 80/20 validation split (seed 42); validation evaluates one 80%-prefix observation from each held-out engine. Feature construction uses cycle plus trailing-window summaries of the three settings and 21 sensors. Feature filtering is fit on training data only. The saved artifact contains preprocessing and estimator. The official FD001 test protocol fits using all training engines, predicts the last observed row of each test engine, then reads `RUL_FD001.txt` only for final scoring. Inference loads test histories without reading the RUL label file.

The reusable prediction interface is `FD001RULModel.load(path).predict_history(history)` in `backend/app/services/ml/fd001_model.py`; `load_engine_histories(data_dir, split="test")` provides feature histories without loading target labels. `FD001MLProvider` supplies the app adapter and maps demo aircraft IDs to those fixed test-engine histories.

Latest reproducible run with seed 42: grouped validation RF MAE/RMSE 11.2843/14.5745 cycles (median baseline 62.7000/63.2519); official final-test RF MAE/RMSE 13.7862/18.6998 cycles (median baseline 39.0800/49.8199). These are results on simulated FD001 engines, not evidence of real-aircraft performance. The weaker official-test result relative to the grouped validation split is retained as measured; no tuning claim is made. The generated `.joblib` model and metrics JSON are ignored artifacts and should be recreated with the training command when absent.

To run the app using the local model instead of mock, put the dataset and trained artifact in the documented paths and set the provider explicitly:

```powershell
cd backend
$env:ML_PROVIDER = 'fd001'
uvicorn app.main:app --reload --port 8000
```

Optional overrides are `FD001_DATA_DIR` and `FD001_MODEL_PATH`. The example adapter maps A17, A19, A21, A23, A24, A26, A28, A32, A33, and A35 to simulated test engines 1–10 in order; this is a demo mapping, not a real aircraft/engine identity link. RUL estimates run through the application's validation boundary. The displayed health score is a transparent convenience indicator, `round(100 * min(max(rul_cycles, 0), 125) / 125)`, and risk bands derive from that score under the shared policy. Neither value is a calibrated failure probability. Since FD001 has only RUL labels, its `failure_probability` is intentionally null. It does not identify a failing subsystem; select one during human triage to create a work order. Cycle values are not converted to hours or calendar dates.

On FD001 startup and explicit **Reset demo**, the app retains the aircraft and inventory catalog, clears mock-seeded events/work orders/transfers/history, and records current FD001 predictions. Only high/critical policy signals create generic open triage events; these events have no inferred subsystem, component, or flight-hour deadline. This prevents mock scenario evidence from being shown beside real-provider output. Maintenance completion updates the inventory/work-order workflow, but the fixed simulated history does not advance to post-repair telemetry; the latest prediction can therefore remain AT_RISK after a completed work order. No model-confirmed return-to-service result is claimed.

To load the opt-in six-case synthetic operations fixture over those same FD001 predictions, also set `DEMO_SCENARIO=fd001_operations`. This replaces only the in-memory demo scenario at startup or Commander-authorized reset; unset it to return to the clean FD001 state. The fixture does not alter the model or dataset. See [the operations demo guide](docs/fd001-operations-demo.md) for its scenarios, reset, API/UI walkthrough, and inventory accounting.

## Recommendation and impact logic

Resource search applies hard constraints first: valid catalog component, transferable unreserved stock above required reserve, and minimum component condition. Rejected options remain in the response with `feasible: false` and a reason. Only feasible candidates are ranked.

The primary objective is the lowest estimated recovery time: transfer ETA plus the work order's planned repair duration. The POC does not have measured evidence to shorten a repair based on part condition, so component condition remains a supporting factor without a time credit. Equal recovery estimates use donor impact, ETA, distance, then base ID as deterministic tie-breaks. The numeric score is included for comparison but cannot override recovery time. Recommendations include their rank and an explanation.

Readiness what-if planning uses the same minimum-condition and available-stock checks for an in-transit arrival that maintenance start uses. For mixed-grade pooled inventory lines it conservatively projects the lower condition, so a transfer is not counted as enabling repair if the resulting line is still unusable. The projection does not model per-unit lots or net multiple unreceived shipments into one destination line.

FD001 events have no model-derived subsystem, so an operator must choose a component during human triage using the maintenance case UI or `POST /api/maintenance/events/{event_id}/work-order` with a catalogued `required_component`. Known subsystem rules restrict the choice to their listed candidates; unmatched FD001 events accept any catalogued component because this demo has no aircraft-level engineering compatibility or airworthiness data. `POST /api/recommendations/{aircraft_id}/reject` records an audit event only: it does not move inventory, create a transfer, or persist a terminal rejection decision. A later explicit Commander approval remains possible. Approval is idempotent while the transfer is in transit and is blocked after receipt or later work-order lifecycle states.

Impact is returned as an estimate at each candidate's expected recovery time. It separates current fleet availability from projected availability, shows the destination-base change, and reports donor transferable stock and an open-work-order stockout indicator. The POC does not convert donor inventory risk into a precise aircraft outage because there is no validated relationship for that calculation. Projections assume no other aircraft changes availability during the interval and do not represent actual outcomes.

`GET /api/aircraft/{aircraft_id}/maintenance-timeline` returns a read-only case view across prediction history, predicted events, work orders, stored recommendation evaluations, approval/rejection decisions, transfers, and audit entries. Add `?work_order_id=WO-...` to focus on one aircraft work order; a work order belonging to another aircraft returns 404. The service joins only explicit stored IDs and never runs a fresh recommendation evaluation while serving the timeline. New prediction ingestion records history IDs on generated events. When ingestion reuses a legacy event, the new history observation is linked as a later observation but the original trigger remains `legacy_unknown`; timestamps are not used to invent that causal link. Work-order and transfer timeline rows show their current status snapshot, with `created_at` identified as the row time; actual transitions appear as separate audit entries. Recommendation rows show the candidate recorded at evaluation time, which may differ from today's inventory.

## Inventory, transfers, and persistence

Inventory lines distinguish total `quantity`, `reserved`, `minimum_reserve`, and `available_for_transfer`. The shared calculation is `max(0, quantity - reserved - minimum_reserve)`. Direct Logistics transfer approval can request an audited minimum-reserve override; reserved stock remains protected. Commander recommendation approval can select an alternate donor only among candidates that pass hard feasibility checks. Its `allow_reserve_override` flag does not make a reserve-infeasible candidate selectable. The source quantity decreases once at dispatch; destination quantity increases once at receipt. A pending transfer can be cancelled. An in-transit transfer cannot be cancelled because its stock has left the source.

Inventory condition is stored on an aggregate base/component line rather than by serialized unit. Current fixtures and allocation rules treat the line's condition as applying to its units. When different grades are received into an already-stocked line, the line keeps the lower condition to avoid upgrading existing lower-grade stock; this conservative summary can understate the better incoming units. The system does not retain per-unit/lot condition provenance.

Maintenance start reserves one transferable component for that work order. Completion consumes that reserved unit once and is idempotent on repeats. Concurrent in-memory transitions are serialized by an `RLock`. These guarantees apply only within one running process; they are not database transactions and do not coordinate multiple server processes.

All application state is in memory and resets on restart. There is no database, migration, or restart persistence. The repository interfaces provide a future persistence boundary, but PostgreSQL/SQLAlchemy remain planned work.

## Demo permissions and security limits

The UI sends `X-Demo-Role` with `commander`, `base`, or `logistics`; Base Manager actions also send `X-Demo-Base` with the selected base. The backend checks the requested capability, validates any supplied base against the known bases, and ensures Base Manager actions target that base. `DEMO_PERMISSION_MODE` defaults to `hardened`: every protected mutation requires an explicit role header, Base Manager mutations require a matching base header, and legacy actor/body/query values cannot replace a supplied role header. `DEMO_PERMISSION_MODE=compat` is an explicit migration option for older headerless clients and restores their actor/default-role fallback; do not use it as a production security setting. `POST /api/demo/reset` is disabled unless `DEMO_RESET_ENABLED=true` is explicitly set, in either mode.

These values remain demo role claims supplied by the caller; anyone can choose a role or base. They are not authenticated identities or production authorization. The API does not enforce read authorization. Production use requires authenticated users, server-verified role and base assignments, server-side authorization for reads and writes, deployment-specific CORS settings, and persistent transactional storage. The demo reset intentionally reinitializes in-memory data and clears prior operational and audit history before recording its reset event.

The capability matrix is available from `GET /api/audit/permissions`. Commander approval, Base Manager maintenance/resource actions, and Logistics inventory/transfer actions are enforced on state-changing routes. Reset requires an explicit Commander role claim and the independent reset-enable setting.

## Recommendation policy evaluation

`app.evaluation.recommendation_baseline` compares the policy with nearest-feasible-source selection on the same deterministic simulated scenarios. The current four cases include one controlled case where the recommendation reaches recovery sooner, two ties, and one case with no feasible source; the baseline is faster in none. These results describe only the simulated cases and do not establish real-world performance. The evaluation code is separate from live operational decisions.

## Project structure and limitations

```text
backend/app/routers/       FastAPI API and compatibility routes
backend/app/services/ml/   mock and FD001 model, trainer, provider adapter
backend/app/services/      recommendation, impact, maintenance, transfer
backend/app/repositories/  in-memory state and repositories
backend/app/domain/        workflow enums and subsystem knowledge rules
CMAPSSData/                locally acquired raw NASA dataset (ignored)
backend/models/            generated trained artifact and metrics (ignored)
frontend/src/              React pages and API integration
```

The existing legacy API routes remain in place with additive fields. Generated `frontend/dist/` output and `frontend/node_modules/` are ignored by `frontend/.gitignore`; dependency manifests and lockfiles are retained. The project remains a synthetic POC: C-MAPSS is an actual trained local model path over simulated engine trajectories, while no real aircraft telemetry, subsystem classifier, calibrated probability, authenticated identity, database persistence, post-maintenance inference, or operational validation is included.
