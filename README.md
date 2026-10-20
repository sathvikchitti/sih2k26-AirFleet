# Aircraft Fleet Readiness & Sustainment Platform

<!-- GENERATED EVIDENCE SUMMARY START -->
- Problem: aircraft condition, maintenance, and spares records are fragmented, delaying readiness decisions.
- Solution: an integrated FD001 RUL demo links model evidence to human-approved maintenance and resource workflows.
- Measured: FD001 official-test MAE/RMSE 13.79/18.70 cycles; across 300 paired synthetic scenarios, Sharing minus local-only was +5.05 pp availability (95% paired CI +4.85 to +5.24) and -4.04 censored aircraft-days lost (95% paired CI -4.19 to -3.89); nearest-FCFS differences were inconclusive.
- Run locally: `.\run_demo.ps1` (Windows PowerShell) or `./run_demo.sh` (macOS/Linux).
- Evidence is from NASA C-MAPSS and synthetic fleet scenarios; intervals are uncalibrated and results are not real-fleet performance.
<!-- GENERATED EVIDENCE SUMMARY END -->

Refresh these five lines from the existing model metrics and scale-simulation JSON with `python scripts/update_readme_summary.py`; this reads the reports without retraining or rerunning simulations.

A deterministic proof of concept for connecting aircraft condition predictions to maintenance planning, resource search, transfer execution, and fleet availability. The recommendation engine is decision support: a human must approve a recommendation before a transfer starts.

## Run the FD001 demo

The one-command launchers run the trained local FD001 provider with the six-case `fd001_operations` fixture. Python 3.14 was verified for the local backend install; use a virtual environment and install backend dependencies, then run `npm ci` from `frontend/` for the UI. The Dockerfile uses Python 3.12; the security verification report records its container build and smoke checks. The repository includes the model artifact and FD001 source files; the launcher fails clearly if required files are missing and never retrains the model. FD001 data is simulated engine history, mapped to demo aircraft IDs; it is not live aircraft telemetry.

On Windows, create and activate an isolated backend environment from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

On macOS or Linux, use `python3.14 -m venv .venv`, activate with `source .venv/bin/activate`, and run `python -m pip install -r backend/requirements.txt`. Install frontend dependencies with `npm ci` from `frontend/`.

On Windows, from the repository root:

```powershell
.\run_demo.ps1
```

On macOS/Linux, from the repository root:

```bash
chmod +x ./run_demo.sh
./run_demo.sh
```

Both launchers default to the frontend at `http://localhost:5173` and backend at `http://127.0.0.1:8000`. They check both loopback ports before starting and never stop an existing process. Keep the launcher running while using the demo; Ctrl+C stops only the backend and frontend processes it started. Logs are written under `backend/` and ignored by Git. If a port is occupied, choose unused ports. PowerShell accepts `-BackendPort 8011 -FrontendPort 5179`; Bash accepts `DEMO_BACKEND_PORT=8011 DEMO_FRONTEND_PORT=5179 ./run_demo.sh`. The frontend uses the same-origin `/api` proxy: `API_PROXY_TARGET` is server-only and `VITE_API_BASE` is explicitly empty.

For an explicit API rehearsal on a disposable loopback demo, run `python scripts/demo_api_rehearsal.py --base-url http://127.0.0.1:8000` for a read-only preflight. Add `--allow-demo-mutations` only when you intend the script to request, approve, receive, triage, start, and complete operations in that in-memory instance. The script never resets state and refuses mutation mode on non-loopback URLs; use a fresh disposable launcher instance for this sequence.

The same demo can run in Docker when Docker Engine and Compose are installed:

```powershell
docker compose up --build
```

Compose binds both services to loopback and now uses restricted evaluator access with reset disabled. Configure `DEMO_BASIC_USERS` and `FRONTEND_ORIGINS` as described below before starting; without accounts the API stays locked. To avoid occupied default ports, set `DEMO_BACKEND_PORT` and `DEMO_FRONTEND_PORT` in the environment before `docker compose up --build` (for example `8011` and `5179`). The backend image copies the existing model artifact and local `CMAPSSData`. Use `docker compose down` to stop only the containers you started.

See `docs/security-hardening-verification.md` for the current build and deployment verification results.

The launchers require already-installed dependencies. For the manual development workflow, the backend uses FastAPI and in-memory repositories, while the frontend uses React and Vite:

```powershell
cd backend
pip install -r requirements.txt
$env:DEMO_ACCESS_MODE = 'local'
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
$env:API_PROXY_TARGET = 'http://127.0.0.1:8000'
$env:VITE_API_BASE = ''
npm run dev
```

Open http://localhost:5173. The manual backend command above uses port 8000, so set the Vite server-only `API_PROXY_TARGET` to that port as shown; the Vite default is port 8002. Keep `VITE_API_BASE` empty so requests use the same-origin proxy. `FRONTEND_ORIGINS` optionally configures the comma-separated list of allowed browser origins; the default allows `http://localhost:5173` and `http://127.0.0.1:5173`. Credentialed CORS is disabled.

For macOS/Linux, set the same variables in the frontend terminal before `npm run dev`:

```bash
export API_PROXY_TARGET=http://127.0.0.1:8000
export VITE_API_BASE=
npm run dev
```

Reset is off by default. Explicitly enable it with `.\run_demo.ps1 -EnableReset` or `DEMO_RESET_ENABLED=true ./run_demo.sh`; the Commander can then use **Reset demo** or `POST /api/demo/reset`. For manual local startup, set `DEMO_RESET_ENABLED=true` explicitly. Local mode is for loopback demonstrations only; never publish Vite or a local-mode backend.

## Verification

From `backend/`:

```powershell
python -m tests.test_workflow
python -m pytest tests/test_fd001_model.py tests/test_fd001_provider.py tests/test_regressions.py tests/test_recommendation_evaluation.py -q
python -m app.evaluation.recommendation_baseline
```

The legacy API compatibility script expects a disposable mock backend at `http://127.0.0.1:8000`. It uses headerless legacy mutations: explicitly set `DEMO_ACCESS_MODE=local`, `ML_PROVIDER=mock`, `DEMO_PERMISSION_MODE=compat`, `DEMO_RESET_ENABLED=true`, and leave `DEMO_SCENARIO` unset for that isolated loopback server. Restricted deployments reject compat mode. Run security tests against restricted mode instead:

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

Risk is calculated by the backend, and a model-supplied risk label is ignored. Health thresholds default to `<45 CRITICAL`, `<60 HIGH`, `<80 MEDIUM`, otherwise `LOW`; set `DEMO_RISK_HEALTH_THRESHOLDS` to a JSON array of three finite, strictly increasing values from 0 through 100 to configure those exclusive upper bounds. For example, `[45,60,80]` preserves the defaults. The backend validates this setting at startup, so restart the server to apply a change. Failure-probability thresholds remain fixed at `>=0.70 CRITICAL`, `>=0.45 HIGH`, `>=0.25 MEDIUM`, otherwise `LOW`. When signals disagree, the more severe band wins. `GET /api/policy/risk-bands` reports the effective thresholds, source, combination rule, and provider-specific health derivation. In mock mode, A17's health score of 41 and failure probability of 0.78 produce `CRITICAL`.

The mock provider emits synthetic, deterministic demo values and identifies its version as `mock-demo-v1`. `prediction_history` contains illustrative seed rows and timestamped provider results; provider-generated mock rows remain marked `is_synthetic: true`. Mock trends are labeled illustrative. FD001 trends are retrospective model inferences over prefixes of simulated engine histories, not observed health telemetry; those histories also carry `is_synthetic: true`. Actual aircraft sensor streams and maintenance outcomes are not available.

## NASA C-MAPSS FD001 model

The local model path uses the official NASA Ames Prognostics Center of Excellence C-MAPSS simulated turbofan data. The canonical [Data.gov dataset record](https://catalog.data.gov/dataset/cmapss-jet-engine-simulated-data) links NASA's [CMAPSSData.zip](https://data.nasa.gov/docs/legacy/CMAPSSData.zip); the NASA [PCoE data repository](https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/) describes the turbofan degradation simulation. This repository bundles FD001's `train_FD001.txt`, `test_FD001.txt`, `RUL_FD001.txt`, and source `readme.txt` under `CMAPSSData/`; the files are stored without line-ending conversion. They contain 100 engine train series, 100 test series, and 100 official final RUL labels. The bundled copies have no signed checksum manifest, so their chain of custody cannot be independently verified; their current SHA-256 values are recorded in the release verification report.

Training is optional; the launchers use the bundled production artifact and do not train. If you deliberately evaluate a new model, install backend dependencies in an isolated environment and train to a separate candidate path from `backend/`:

```powershell
python -m app.services.ml.train_fd001 --artifact models/cmapss_fd001_rf_v1_candidate.joblib --metrics models/cmapss_fd001_rf_v1_candidate_metrics.json --reference-artifact models/cmapss_fd001_rf_v1.joblib
```

The script fits a 200-tree Random Forest to run-to-failure training RUL targets capped at 125 cycles. It creates a deterministic engine-grouped 80/20 validation split (seed 42); validation evaluates one 80%-prefix observation from each held-out engine. Feature construction uses cycle plus trailing-window summaries of the three settings and 21 sensors. Feature filtering is fit on training data only. The saved artifact contains preprocessing and estimator. The official FD001 test protocol fits using all training engines, predicts the last observed row of each test engine, then reads `RUL_FD001.txt` only for final scoring. Inference loads test histories without reading the RUL label file.

The reusable prediction interface is `FD001RULModel.load(path).predict_history(history)` in `backend/app/services/ml/fd001_model.py`; `load_engine_histories(data_dir, split="test")` provides feature histories without loading target labels. `FD001MLProvider` supplies the app adapter and maps demo aircraft IDs to those fixed test-engine histories.

Latest reproducible run with seed 42: grouped validation RF MAE/RMSE 11.2843/14.5745 cycles (median baseline 62.7000/63.2519); official final-test RF MAE/RMSE 13.7862/18.6998 cycles (median baseline 39.0800/49.8199). These are results on simulated FD001 engines, not evidence of real-aircraft performance. The weaker official-test result relative to the grouped validation split is retained as measured; no tuning claim is made. The repository includes the fitted `cmapss_fd001_rf_v1.joblib` artifact and its NASA C-MAPSS source files for reproducible local use; the saved metrics JSON is a tracked reference report. The command above writes a candidate artifact and report and scores the bundled artifact read-only.

`GET /api/ml/fd001/metrics` returns a validated read-only projection of the saved official-test metrics reference for the existing RF artifact. It reports the scoring protocol, artifact version/hash, and results for 100 test engines. The raw per-engine p10–p90 RF tree interval has nominal coverage 80%; observed coverage was 70%. The separate mean-inclusive envelope (the raw bounds expanded when necessary to include the forest mean) also had observed coverage 70%; no nominal coverage is assigned to this expanded envelope. Both are uncalibrated. The route reads the saved metrics JSON and does not retrain or rescore. Missing, corrupt, or invalid metrics produce HTTP 503 with `metrics_status: "unavailable"`. This endpoint is distinct from `GET /api/evaluation/summary`, which serves aggregate synthetic fleet-policy results.

To run the app using the local model instead of mock, put the dataset and trained artifact in the documented paths and set the provider explicitly:

```powershell
cd backend
$env:ML_PROVIDER = 'fd001'
uvicorn app.main:app --reload --port 8000
```

Optional overrides are `FD001_DATA_DIR` and `FD001_MODEL_PATH`. The example adapter maps A17, A19, A21, A23, A24, A26, A28, A32, A33, and A35 to simulated test engines 1–10 in order; this is a demo mapping, not a real aircraft/engine identity link. RUL estimates run through the application's validation boundary. The displayed health score is a transparent convenience indicator, `round(100 * min(max(rul_cycles, 0), 125) / 125)`, and risk bands derive from that score under the shared policy. Neither value is a calibrated failure probability. Since FD001 has only RUL labels, its `failure_probability` is intentionally null. It does not identify a failing subsystem; select one during human triage to create a work order. Cycle values are not converted to hours or calendar dates.

On FD001 startup and explicit **Reset demo**, the app retains the aircraft and inventory catalog, clears mock-seeded events/work orders/transfers/history, and records current FD001 predictions. Only high/critical policy signals create generic open triage events; these events have no inferred subsystem, component, or flight-hour deadline. This prevents mock scenario evidence from being shown beside real-provider output. The risk-policy note in Commander and aircraft detail reads `/api/policy/risk-bands`, so it displays the backend's current startup-loaded threshold values. Maintenance completion updates the inventory/work-order workflow, but the fixed simulated history does not advance to post-repair telemetry; the latest prediction can therefore remain AT_RISK after a completed work order. No model-confirmed return-to-service result is claimed.

### Indicative cycle-based spares forecast

With the FD001 provider selected, `GET /api/resources/forecast?horizon_cycles=30` returns per-base/per-engine-component expected demand, physical stock, reserve/condition constraints, and feasible whole-unit donor suggestions. Demand sums the per-aircraft normal approximation `P(RUL cycles <= horizon)` from finite RUL point/std/envelope values; it stays fractional until a projected unit shortfall is calculated. This estimate is explicitly indicative and uncalibrated. It is not the provider's `failure_probability`, a subsystem classification, or a component diagnosis. Flight-hour mock predictions and predictions with missing/invalid cycle uncertainty are unavailable; valid intervals outside the horizon are counted separately. No eligible predictions yields null expected demand, distinct from a valid zero expected-demand result.

The forecast uses the read-only shared allocation preview to account for open work orders and pending/in-transit transfer commitments before suggesting stock. Open work orders for the same aircraft/component are excluded from future probabilistic demand; linked inbound or proposed WO stock is not reused to cover other aircraft's forecast demand. Only unbound, serviceable inbound units above reserves can reduce forecast shortfall. The endpoint keeps the post-commitment balance frozen while its deterministic, sequential move suggestions compete on a separate cloned ledger; it is not a global optimizer. Donors must pass the same catalog, condition, unreserved-stock, and minimum-reserve checks used by resource search. Suggestions are not transfers or reservations: Logistics can create a selected move through the existing `POST /api/transfers` endpoint, which rechecks permissions and current inventory. A GET forecast does not mutate operational state.

Because FD001 predicts engine RUL only, the response labels the engine-to-part mapping `assumed mapping for demo`. The built-in demo mapping assigns odd-numbered engines 1–9 to `HP-204` and even-numbered engines 2–10 to `OE-310`; an optional `FD001_ENGINE_PART_MAPPING` environment variable can override it with a JSON object of engine IDs to catalogued Engine-category part numbers, for example `{"1":"HP-204","2":"OE-310"}`. Invalid/non-engine catalog entries fail clearly. This mapping is an operational assumption, not a model result or airworthiness determination.

To load the opt-in six-case synthetic operations fixture over those same FD001 predictions, also set `DEMO_SCENARIO=fd001_operations`. This replaces only the in-memory demo scenario at startup or Commander-authorized reset; unset it to return to the clean FD001 state. The fixture does not alter the model or dataset. See [the operations demo guide](docs/fd001-operations-demo.md) for its scenarios, reset, API/UI walkthrough, and inventory accounting.

## Recommendation and impact logic

Resource search applies hard constraints first: valid catalog component, transferable unreserved stock above required reserve, and minimum component condition. Rejected options remain in the response with `feasible: false` and a reason. Only feasible candidates are ranked.

The primary objective is the lowest estimated recovery time: transfer ETA plus the work order's planned repair duration. The POC does not have measured evidence to shorten a repair based on part condition, so component condition remains a supporting factor without a time credit. Equal recovery estimates use donor impact, ETA, distance, then base ID as deterministic tie-breaks. The numeric score is included for comparison but cannot override recovery time. Recommendations include their rank and an explanation.

Readiness what-if planning uses the same minimum-condition and available-stock checks for an in-transit arrival that maintenance start uses. For mixed-grade pooled inventory lines it conservatively projects the lower condition, so a transfer is not counted as enabling repair if the resulting line is still unusable. The projection does not model per-unit lots or net multiple unreceived shipments into one destination line.

FD001 events have no model-derived subsystem, so an operator must choose a component during human triage using the maintenance case UI or `POST /api/maintenance/events/{event_id}/work-order` with a catalogued `required_component`. Known subsystem rules restrict the choice to their listed candidates; unmatched FD001 events accept any catalogued component because this demo has no aircraft-level engineering compatibility or airworthiness data. `POST /api/recommendations/{aircraft_id}/reject` records an audit event only: it does not move inventory, create a transfer, or persist a terminal rejection decision. A later explicit Commander approval remains possible. Approval is idempotent while the transfer is in transit and is blocked after receipt or later work-order lifecycle states.

Impact is returned as an estimate at each candidate's expected recovery time. It separates current fleet availability from projected availability, shows the destination-base change, and reports donor transferable stock and an open-work-order stockout indicator. The POC does not convert donor inventory risk into a precise aircraft outage because there is no validated relationship for that calculation. Projections assume no other aircraft changes availability during the interval and do not represent actual outcomes.

Fleet overview also exposes `mission_capable_rate_pct` (the existing AVAILABLE-aircraft share), `readiness_target_pct`, and `gap_to_target_pct` (the nonnegative shortfall in percentage points). `READINESS_TARGET_PCT` configures the target from 0 through 100 and defaults to 75. `aircraft_down_for_maintenance` counts MAINTENANCE and WAITING_FOR_PART states. `nmcs_count` is a synthetic resource-shortage proxy: distinct non-AVAILABLE aircraft with an active work order whose catalogued required component cannot claim serviceable local inventory. Reserved units count only when the aggregate stock condition remains above the component minimum; pending and in-transit shipments are not counted as local stock until receipt. Unknown or unselected components are not inferred. These workflow indicators are not official mission-capability or airworthiness determinations.

`GET /api/aircraft/{aircraft_id}/maintenance-timeline` returns a read-only case view across prediction history, predicted events, work orders, stored recommendation evaluations, approval/rejection decisions, transfers, and audit entries. Add `?work_order_id=WO-...` to focus on one aircraft work order; a work order belonging to another aircraft returns 404. The service joins only explicit stored IDs and never runs a fresh recommendation evaluation while serving the timeline. New prediction ingestion records history IDs on generated events. When ingestion reuses a legacy event, the new history observation is linked as a later observation but the original trigger remains `legacy_unknown`; timestamps are not used to invent that causal link. Work-order and transfer timeline rows show their current status snapshot, with `created_at` identified as the row time; actual transitions appear as separate audit entries. Recommendation rows show the candidate recorded at evaluation time, which may differ from today's inventory.

## Inventory, transfers, and persistence

Inventory lines distinguish total `quantity`, `reserved`, `minimum_reserve`, and `available_for_transfer`. The shared calculation is `max(0, quantity - reserved - minimum_reserve)`. Direct Logistics transfer approval can request an audited minimum-reserve override; reserved stock remains protected. Commander recommendation approval can select an alternate donor only among candidates that pass hard feasibility checks. Its `allow_reserve_override` flag does not make a reserve-infeasible candidate selectable. The source quantity decreases once at dispatch; destination quantity increases once at receipt. A pending transfer can be cancelled. An in-transit transfer cannot be cancelled because its stock has left the source.

Inventory condition is stored on an aggregate base/component line rather than by serialized unit. Current fixtures and allocation rules treat the line's condition as applying to its units. When different grades are received into an already-stocked line, the line keeps the lower condition to avoid upgrading existing lower-grade stock; this conservative summary can understate the better incoming units. The system does not retain per-unit/lot condition provenance.

Maintenance start reserves one transferable component for that work order. Completion consumes that reserved unit once and is idempotent on repeats. Concurrent in-memory transitions are serialized by an `RLock`. These guarantees apply only within one running process; they are not database transactions and do not coordinate multiple server processes.

All application state is in memory and resets on restart. There is no database, migration, or restart persistence. The repository interfaces provide a future persistence boundary, but PostgreSQL/SQLAlchemy remain planned work.

## Evaluator access and deployment security

`DEMO_ACCESS_MODE` defaults to `restricted`. Standard HTTP Basic authentication gates all application routes, including reads, mutations, `/docs`, and `/openapi.json`. Only `/livez` (a minimal liveness response) and CORS preflights are public. Without configured accounts the API returns 503; missing, malformed, or incorrect credentials return a generic 401 challenge. Password comparison follows the [FastAPI HTTP Basic guidance](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/).

`DEMO_BASIC_USERS` is a **backend-only** JSON object mapping usernames to `{ "password": "<unique random password of at least 20 ASCII characters>", "role": "commander|base|logistics", "base": "alpha" }`. `base` is required only for a Base Manager account and must be a known base. Use a unique random password per account, distribute it privately, and remove the accounts after evaluation. Keep this variable in your host's secret configuration; never in Git, frontend `.env`, `VITE_*`, image build arguments, URLs, or screenshots. Do not publish `docker compose config` output containing interpolated secrets.

In restricted mode the middleware discards every incoming `X-Demo-Role` and `X-Demo-Base` value and supplies the authenticated account's role/base to the existing permission checks. UI role selection cannot grant privileges. Body and query actors cannot override the account. Commander approves recommendations, Base Manager handles maintenance within its assigned base, and Logistics manages inventory/transfers. All authenticated evaluator accounts can read the synthetic fleet across bases; per-base read confidentiality is outside this demo's scope.

`DEMO_ACCESS_MODE=local` explicitly retains caller-selected demo roles for loopback development. `X-Demo-Role` alone is **not production authentication**. `DEMO_PERMISSION_MODE` defaults to `hardened`; `compat` is allowed only in local mode for isolated legacy tests. The launchers bind loopback and refuse an explicitly restricted access mode rather than silently downgrading it. Do not run them as hosted launchers. On Bash, use `export DEMO_ACCESS_MODE=local` for manual development; PowerShell uses `$env:DEMO_ACCESS_MODE='local'`.

`DEMO_RESET_ENABLED` defaults to false in the backend, Docker image, Compose, and launchers. Local reset requires `.\run_demo.ps1 -EnableReset` or `DEMO_RESET_ENABLED=true ./run_demo.sh` plus the Commander demo role. Restricted reset, if deliberately enabled outside the supplied Compose configuration, also requires authenticated Commander credentials. Reset erases the previous operational/audit history before recording the reset event. Hosted Compose fixes reset to false.

To run the restricted evaluator deployment:

1. Install Docker Engine/Compose on the host. Keep ports 8000 and 5173 private. Use one backend process because storage and locking are in memory.
2. Set `DEMO_BASIC_USERS` in the server environment, with separate accounts for the roles you need. A PowerShell setup that prompts without printing passwords is:

   ```powershell
   $env:DEMO_BASIC_USERS = @{
     evaluatorCommander = @{ password = (Read-Host 'Commander random password (20+ ASCII chars)' -MaskInput); role = 'commander' }
     evaluatorAlpha = @{ password = (Read-Host 'Alpha random password (20+ ASCII chars)' -MaskInput); role = 'base'; base = 'alpha' }
     evaluatorLogistics = @{ password = (Read-Host 'Logistics random password (20+ ASCII chars)' -MaskInput); role = 'logistics' }
   } | ConvertTo-Json -Compress
   $env:FRONTEND_ORIGINS = 'https://evaluator.example.org'
   docker compose up --build -d
   ```

   Replace the hostname with your actual HTTPS origin (no trailing slash). On Linux, inject the same JSON via your host's secret manager/environment and set `FRONTEND_ORIGINS` before the same Compose command. For a loopback-only restricted rehearsal, use `http://localhost:5173,http://127.0.0.1:5173` instead.
3. Put an existing HTTPS reverse proxy in front of **only** `127.0.0.1:5173`, preserve `Host` and `Authorization`, and restrict evaluator source IPs or require a VPN. For example, adapt this host Nginx server block with your real certificate paths and evaluator IP; do not expose the internal HTTP ports:

   ```nginx
   server {
       listen 443 ssl;
       server_name evaluator.example.org;
       ssl_certificate /etc/letsencrypt/live/evaluator.example.org/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/evaluator.example.org/privkey.pem;
       allow 203.0.113.10; # replace with the evaluator's actual public IP
       deny all;
       location / {
           proxy_pass http://127.0.0.1:5173;
           proxy_set_header Host $host;
           proxy_set_header Authorization $http_authorization;
       }
   }
   ```

4. Visit `https://evaluator.example.org/login` to get the browser's Basic login prompt and redirect to the application. Choose the UI view matching the account. To test another role, use a fresh browser profile/private session (Basic has no application logout). The bundled Nginx forwards `/login` and `/api/` to the backend; `VITE_API_BASE` remains empty and no credential enters the client bundle.
5. Verify `/livez` on the private backend returns 200, an unauthenticated `/api/aircraft` returns 401, credentials allow reads, spoofed role headers cannot elevate a Logistics account, and authenticated Commander reset returns 403. Run `python -m pytest tests/test_evaluator_access.py -q` from `backend/` for executable security/workflow checks. Check `docker compose ps` for health. Shut down with `docker compose down` after evaluation and revoke credentials.

`FRONTEND_ORIGINS` has no allowed origins by default in restricted mode; wildcards are rejected. It lists exact trusted browser origins, including the public same-origin proxy URL because browser mutations are checked against it to prevent cross-site requests with cached Basic credentials. CORS remains non-credentialed; use the same-origin proxy for browser Basic access. For separate frontend/backend hosts, prefer proxying `/api` through the frontend origin rather than configuring cross-origin browser credentials. Origin-less CLI requests still require authentication. CORS is not an authentication boundary.

This is time-limited evaluator access, not a production identity platform: no MFA, account recovery, application logout, password hashing at rest, or application rate limiting. Server environment/container administrators can inspect the configured passwords. HTTPS and an evaluator IP restriction/VPN are required for hosting; never send Basic credentials over public HTTP. Public static assets still contain synthetic fallback fixtures; protect the entire frontend at the edge if even those should be private. Use synthetic data only. TLS/edge certificate provisioning must be verified on your actual host before sharing a URL; otherwise keep the deployment private. State resets on restart and cannot safely span multiple workers. The proof of concept is not certified or suitable for operational military decisions.

## Recommendation policy evaluation

`app.evaluation.recommendation_baseline` compares the policy with nearest-feasible-source selection on the same deterministic simulated scenarios. The current four cases include one controlled case where the recommendation reaches recovery sooner, two ties, and one case with no feasible source; the baseline is faster in none. These results describe only the simulated cases and do not establish real-world performance. The evaluation code is separate from live operational decisions.

## Roadmap and release boundary

This delivery completes the planned work through Phase 5: FD001 model integration and uncertainty reporting, readiness indicators, cycle-based spares forecasting, and paired synthetic allocation-policy evaluation. Phase 6 telemetry replay and Phase 7 external maintenance/spares imports are deferred; this repository does not contain an end-to-end replay of real operational telemetry or governed external-agency imports. Future work also needs authenticated identities and read authorization, persistent transactional storage, real aircraft/engine/component mappings, validated post-maintenance telemetry, and operational/airworthiness validation. The current system remains a synthetic proof of concept, not a certified maintenance or flight-release system.

## Project structure and limitations

```text
backend/app/routers/       FastAPI API and compatibility routes
backend/app/services/ml/   mock and FD001 model, trainer, provider adapter
backend/app/services/      recommendation, impact, maintenance, transfer
backend/app/repositories/  in-memory state and repositories
backend/app/domain/        workflow enums and subsystem knowledge rules
CMAPSSData/                bundled NASA C-MAPSS FD001 source files (byte-preserved)
backend/models/            bundled fitted FD001 model and tracked metrics reference
frontend/src/              React pages and API integration
```

The existing legacy API routes remain in place with additive fields. Generated `frontend/dist/` output and `frontend/node_modules/` are ignored by `frontend/.gitignore`; dependency manifests and lockfiles are retained. The project remains a synthetic POC: C-MAPSS is an actual trained local model path over simulated engine trajectories, while no real aircraft telemetry, subsystem classifier, calibrated probability, authenticated identity, database persistence, post-maintenance inference, or operational validation is included.
