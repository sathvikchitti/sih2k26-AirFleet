# Final polish verification

This record captures the requested final-push polish by task, with each task's checks recorded after implementation.

## Task 1 — useful first-view forecast horizon

The forecast panel now defaults to 60 cycles while keeping the horizon editable. It offers 30/60/100-cycle quick-select buttons. When the response has `forecast_status: "no_eligible_predictions"`, the panel can report a larger tested horizon from the additive `suggested_horizon_cycles` field; the backend computes the smallest of 60, 100, or 125 cycles with an eligible prediction using the already-fetched, mapped, non-work-order-covered predictions. It does not refetch or recursively run the forecast. A null suggestion remains an honest no-suggestion state.

Changed files:

- `backend/app/services/demand_forecast_service.py` — computes the optional tested-horizon suggestion.
- `backend/tests/test_demand_forecast.py` — covers the smallest qualifying horizon, exclusions for open work orders, no qualifying horizon, and mock-hour predictions.
- `frontend/src/components/ResourceForecastPanel.jsx` — 60-cycle default, editable input, quick-selects, and explanatory empty-state text.
- `frontend/scripts/render-check/entry.jsx` — SSR checks for the default/control choices and both suggested and absent suggestions.

Verification outputs:

```text
Backend focused (from backend/):
python -m pytest tests/test_demand_forecast.py -q --basetemp .pytest-tmp-task1-focused
22 passed in 0.46s

Backend full (from backend/):
python -m pytest tests -q --ignore=tests/test_api_compat.py --basetemp .pytest-tmp-task1-full
251 passed in 93.10s

Frontend (from frontend/):
npm run verify:views
19/19 views passed

npm run build
passed (56 modules)

node --test scripts/prediction-contract.test.mjs
3/3 passed
```

The compatibility suite was not part of the full command because it targets a mutable API server; no live demo state was reset for these checks. A prior read-only GET probe against the then-running demo on port 8011 showed the pre-change baseline: at 30 cycles, 0 eligible / 9 outside horizon / 0 unavailable / 0 moves; at 60 cycles, 2 / 7 / 0 / 0; at 100 cycles, 6 / 3 / 0 / 0. This records why the default horizon and empty-state guidance were changed; the probe was not a post-change server verification and did not test the new response field over HTTP.

## Task 2 — alternate engine-category mapping

The default demo map now assigns odd-numbered FD001 engines to `HP-204` and even-numbered engines to `OE-310`. This avoids concentrating every mapped engine forecast on one part category and lets the forecast service identify feasible moves using its existing stock, reserve, condition, and shared-allocation rules. The mapping remains a demo assumption; it does not assert real engine/component fit. The validated `FD001_ENGINE_PART_MAPPING` override remains available.

Changed files:

- `backend/app/domain/knowledge.py` — changes only the default demo mapping; explicit override validation is retained.
- `backend/tests/test_demand_forecast.py` — verifies the alternating default mapping and preserves override behavior.
- `docs/final-changes.md` — updates the API/demo mapping description.
- `README.md` — corrects the user-facing default mapping description.

Verification outputs:

```text
Backend focused (from backend/):
python -m pytest tests/test_demand_forecast.py -q --basetemp .pytest-tmp-task2-focused
23 passed in 0.36s

Backend full (from backend/):
python -m pytest tests -q --ignore=tests/test_api_compat.py --basetemp .pytest-tmp-task2-full
252 passed in 92.48s

Frontend (from frontend/; no source changes in Task 2):
npm run build
passed (56 modules, 6.50s)

npm run verify:views
19/19 views passed

node --test scripts/prediction-contract.test.mjs
3/3 passed
```

Read-only isolated-process forecast probe at the default 60-cycle horizon, using the new map and the synthetic FD001 operations fixture, found 2 eligible predictions and 7 outside the horizon. It proposed one feasible `HP-204` move from Charlie to Bravo (one unit, 260 km, 4.3 h ETA); Bravo's HP-204 demand was 0.1781 with a unit at its minimum reserve and shortfall 1. Charlie's `OE-310` demand was 0.4215 with quantity 3, minimum reserve 3, and no transferable stock. Charlie's HP-204 stock was quantity 1, reserved 0, minimum reserve 0, and transferable 1 before the suggestion; the cloned ledger debited that single proposed unit, leaving 0 afterward. No real inventory was changed. This is a deterministic demo forecast, not evidence that the map is valid for operational aircraft.

## Task 3 — first useful forecast move in the default demo

No scenario inventory or fixture values were changed. The Task 2 alternating map exposed a feasible default-horizon forecast proposal using the existing shared stock and reserve rules. The read-only forecast does not reserve stock or create transfers. A Logistics request is a separate `POST /api/transfers` action that creates a pending request; approval/dispatch and receipt remain distinct workflow steps. The operations guide now includes the exact request body/header example and records that current stock must be rechecked before submission.

Measured probe at 60 cycles: 2 eligible predictions, 7 outside horizon, and one proposed HP-204 unit from Charlie to Bravo, with estimated 4.3 h ETA and 260 km distance. Bravo's expected HP-204 demand was 0.1781; its one unit was at minimum reserve, with projected shortfall 1. Charlie's HP-204 stock was quantity 1, reserved 0, minimum reserve 0, and transferable 1 before the proposal, then transferable 0 in the cloned preview after the virtual debit. Charlie's OE-310 expected demand was 0.4215 with quantity 3 at minimum reserve 3 and no transferable units. These are synthetic forecast values, not predicted component failures or real logistics performance.

Verification outputs:

```text
Backend focused (from backend/):
python -m pytest tests/test_fd001_operations_scenario.py -q --basetemp .pytest-tmp-task3-focused
6 passed in 95.14s

Backend full (from backend/):
python -m pytest tests -q --ignore=tests/test_api_compat.py --basetemp .pytest-tmp-task3-full
253 passed in 110.51s

Frontend (from frontend/):
npm run build
passed (56 modules)

npm run verify:views
19/19 views passed

node --test scripts/prediction-contract.test.mjs
3/3 passed
```

The focused route test checks that forecast GET leaves the repository snapshot unchanged, Commander is denied transfer creation without state changes, and Logistics can create a pending transfer request without moving stock. The frontend refreshes the forecast after a requested move; creation remains a manual action and does not automatically approve or dispatch the transfer.

## Task 4 — paired README comparison

The generated five-line summary now reports Sharing-minus-local-only paired effects from the simulation's paired-delta JSON, not a subtraction of policy marginal means. It reverses the local-only-minus-proposed delta and its confidence-interval endpoints, and converts summed aircraft-hours to aggregate aircraft-days by dividing by 24. A bounded comparison helper test checks the sign and interval transformation. The frontend evaluation headline uses the same paired convention, reports a distinction only when the relevant paired intervals support it, and displays unavailable when intervals are absent.

Measured values from the existing 300-scenario report: Sharing-minus-local-only availability was +5.05 percentage points (95% paired CI +4.85 to +5.24); aggregate censored aircraft-days lost were −4.04 (95% paired CI −4.19 to −3.89). Sharing versus nearest-FCFS has no distinguishable difference in these scenarios because its paired intervals include zero. No model training, scenario rerun, ranking change, or model/simulation JSON update was made for this summary change.

Verification outputs:

```text
README generator (from repository root):
python scripts/update_readme_summary.py
updated the five-line generated summary from the existing JSON reports

python scripts/update_readme_summary.py --check
README evidence summary is current.

Focused generator test (from repository root):
python -m pytest backend/tests/test_readme_summary.py -q
1 passed in 0.04s

Backend full (from backend/):
python -m pytest tests -q --ignore=tests/test_api_compat.py --basetemp .pytest-tmp-task4-full
254 passed in 110.57s

Frontend (from frontend/):
npm run verify:views
19/19 views passed

npm run build
passed (56 modules)

node --test scripts/prediction-contract.test.mjs
3/3 passed
```

## Task 5 — risk policy inspection and disclosure

The backend exposes its effective health-risk bands through `GET /api/policy/risk-bands`. The default health cutoffs remain 45/60/80, while `DEMO_RISK_HEALTH_THRESHOLDS` can set exactly three finite, in-range, strictly ascending cutoffs at server startup. Failure-probability bands remain fixed at 0.70/0.45/0.25, and conflicting health/probability signals still select the more severe band. The new UI note on Commander and aircraft detail reads the endpoint rather than carrying a second threshold table. For FD001, the policy metadata exposes the existing health-from-RUL formula and 125-cycle cap; probability remains null/unavailable and no subsystem is inferred.

The initial risk-policy probe found those thresholds hard-coded. Task 5 makes only the health-score cutoffs configurable and reports the effective policy; it does not alter the band ordering, the probability thresholds, or the existing default health calculation.

Focused verification outputs:

```text
Backend (from backend/):
python -m pytest tests/test_risk_policy.py tests/test_regressions.py tests/test_fd001_provider.py -q --basetemp .pytest-tmp-task5-focused-elevated
63 passed in 2.45s
py_compile passed

Backend full (from backend/):
python -m pytest tests -q --ignore=tests/test_api_compat.py --basetemp .pytest-tmp-task5-full
271 passed in 109.09s

Frontend (from frontend/):
npm run verify:views
19/19 views passed

npm run build
passed (57 modules)

node --test scripts/prediction-contract.test.mjs
4/4 passed
```


## Task 6 — saved FD001 official-test metrics

The dedicated read-only route `GET /api/ml/fd001/metrics` projects the saved production-artifact reference from `backend/models/cmapss_fd001_rf_v1_metrics.json`. It reports metrics for 100 engines under the official final-observed-row protocol, with the official RUL labels used for scoring only. The raw RF tree p10–p90 interval is a nominal 80% range with 70% observed coverage; the separately named mean-inclusive envelope also has 70% observed coverage, but no nominal coverage claim. Both widths and all RUL values are in cycles, and both uncertainty methods remain uncalibrated. Missing, corrupt, or invalid saved metrics return HTTP 503 with a generic unavailable status; the route does not train or rescore.

The trend response also carries the actual model version used for the history. This lets the detail view label model provenance from the backend response instead of assuming it from the provider selector. The existing `/api/evaluation/summary` remains the separate synthetic fleet-policy summary route.

Frontend verification (from `frontend/`):

```text
npm run verify:views
19/19 views passed

npm run build
passed (57 modules)

node --test scripts/prediction-contract.test.mjs
5/5 passed
```

Backend focused verification (from `backend/`):

```text
python -m pytest tests/test_fd001_metrics_api.py -q
8 passed in 2.49s

python -m py_compile app/routers/evaluation.py app/services/ml/fd001_provider.py app/services/compatibility.py app/routers/aircraft.py tests/test_fd001_metrics_api.py
passed
```

Backend full verification (from `backend/`):

```text
python -m pytest tests -q --ignore=tests/test_api_compat.py
279 passed in 109.39s
```

The compatibility script was excluded because it targets a mutable API server; no live demo runtime was reset for this check. The production model artifact SHA-256 remains `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`; neither the model artifact nor metrics JSON was modified for Task 6.

## Task 7: bundled runtime assets and fresh-install checks

The initial asset inventory was read-only; packaging changes then made the runtime inputs part of the repository. The production FD001 model SHA-256 is `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`.

- Task 2 initial finding: before the change, `backend/app/domain/knowledge.py` mapped engines 1–10 to `HP-204`. Task 2 changes the default to odd engines `HP-204`, even engines `OE-310`. The only other catalog part categorized as Engine is `OE-310` (`backend/app/data.py:87–90`). The validated `FD001_ENGINE_PART_MAPPING` override remains (`knowledge.py`); both defaults and overrides are demo assumptions, not aircraft/engine identity facts.
- Task 3 initial finding: the pre-change read-only port-8011 probe returned no suggested moves at 30, 60, or 100 cycles. At 100 cycles, Alpha HP-204 expected demand was `0.4707`, stock/free `0`, shortfall `1`; Bravo demand `1.5970`, quantity `1`, minimum reserve `1`, transferable `0`, shortfall `2`; Charlie demand `1.4431`, quantity/free `1`, forecast-protected `1`, shortfall `1`. That was the all-HP-204 mapping and pre-change running process. After Task 2, the isolated 60-cycle probe described above found a feasible Charlie-to-Bravo HP-204 suggestion. These are different mapping snapshots; no fixture or inventory was altered.
- The bundled model is 19,662,518 bytes. The four required NASA inputs (`train_FD001.txt`, `test_FD001.txt`, `RUL_FD001.txt`, and `readme.txt`) total 5,747,082 bytes; model plus inputs total 25,409,600 bytes (25.41 decimal MB; 24.23 MiB). `.gitignore` now unignores only these four files and `backend/models/cmapss_fd001_rf_v1.joblib`; `.gitattributes` uses `-text`/binary for these files so checkout filters cannot rewrite source bytes. SHA-256 values: model `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`, train `963B5E22825B34D8B21C69E1AEB4AF3E647050EB672EE8834BA4B5D91D2DE0F8`, test `3CDA7109CE17BAFB5443F2AC926CFCF88154B941B8C4CF95EB55D1DDD6F52851`, RUL `A19C8EC94931949D0485BDC35118206E9C81C4547B422EFB9CF86F4CEDDBCECA`, readme `4F5270554B775C67E73AFF383C5436FD329D6E4CC3D3A116913276FAE511269B`.
- README setup now uses Python 3.14 in a virtual environment, matching the interpreter actually available and verified on this host. The Dockerfile remains based on Python 3.12; Docker is not verified here. The previous pins FastAPI 0.115.6, Uvicorn 0.34.0, and Pydantic 2.10.4 did not provide a Pydantic Core 2.27.2 wheel for CPython 3.14. A binary-only query (`python -m pip download --only-binary=:all: --no-deps --dest backend/.pytest-tmp-task7-wheel-probe --python-version 3.14 --implementation cp --abi cp314 --platform win_amd64 pydantic-core==2.27.2`) confirmed no matching wheel, and a source build made no progress. Only those three web-stack pins were updated to FastAPI 0.136.1, Uvicorn 0.46.0, and Pydantic 2.13.3; NumPy 2.4.4, scikit-learn 1.9.0, and joblib 1.5.3 remain unchanged.
- Fresh isolated install verification used the Python 3.14 environment at `C:\Users\bhanodai\.codex\visualizations\2026\10\17\01a14810-55e6-7001-a1e6-028b5b5ebfde\final-polish-venv`. `python -m pip --python <venv> install -r backend/requirements.txt` installed the requirements; after `python -m ensurepip --upgrade`, the standard `<venv>\Scripts\python.exe -m pip install -r <fresh-export>\backend\requirements.txt` succeeded with all requirements satisfied, and `<venv>\Scripts\python.exe -m pip check` returned `No broken requirements found`. Resolved runtime versions were FastAPI 0.136.1, Uvicorn 0.46.0, Pydantic 2.13.3, NumPy 2.4.4, scikit-learn 1.9.0, joblib 1.5.3, SciPy 1.18.1. A `FD001RULModel.load` smoke on the bundled artifact returned model version `cmapss-fd001-rf-v1` and test-engine-3 prediction 52.286680486 cycles (interval 28.225–79.275). The artifact and all four NASA input hashes above are unchanged.
- The fresh export's frontend dependencies installed with `npm ci`; build passed (57 modules), view verification passed (19/19), and prediction contract tests passed (5/5). npm audit reported five high findings in the development dependency tree, including `GHSA-vfj7-8cjw-p6xm` in the braces dependency chain; no major unrelated framework upgrade was made. `docker info` reports CLI 29.4.0 but cannot connect to `npipe:////./pipe/dockerDesktopLinuxEngine`; Docker is not verified on this host.
- Fresh-export launch command from PowerShell, with the isolated environment selected explicitly:

  ```powershell
  $venvScripts = 'C:\Users\bhanodai\.codex\visualizations\2026\10\17\01a14810-55e6-7001-a1e6-028b5b5ebfde\final-polish-venv\Scripts'
  $env:PATH = "$venvScripts;$env:PATH"
  .\run_demo.ps1 -BackendPort 8013 -FrontendPort 5181
  ```

- The launcher ran from `fresh-final-polish/`. Its backend listener was PID 12652 on `127.0.0.1:8013`, and Vite was PID 30788 on `127.0.0.1:5181`. GET `/api/health/A21` returned HTTP 200 with model `cmapss-fd001-rf-v1`, RUL 52.28668 cycles, health 42/CRITICAL, `failure_probability: null`, `is_synthetic: true`, and interval 28.225–79.275. The first sandboxed attempt could not access loopback and timed out; the same launcher succeeded when run with escalation. A read-only browser check on `http://localhost:5181` confirmed the Commander forecast panel, backend-driven risk explanation, A21 synthetic model data and timeline, and one feasible Charlie-to-Bravo HP-204 option (4.3 h, 260 km, 84% condition); no mutation was made during that read-only check.
- The standard-library rehearsal script completed once on the fresh instance with `python scripts/demo_api_rehearsal.py --base-url http://127.0.0.1:8013 --allow-demo-mutations` (elevated). The command was restricted to the disposable loopback export and performed no reset. T-105 moved one HP-204 from Charlie to Bravo: Charlie quantity/transferable changed 1/1→0/0; Bravo quantity changed 1→2 and transferable 0→1. Bravo’s pooled condition remained 42% although the incoming unit was 84%. The existing PM-002/WO-1046 human-selected FP-102 triage returned the same work order; Commander approval and Logistics receipt created and completed transfer T-106 from Alpha to Charlie. Alpha FP-102 quantity/transferable changed 4/3→3/2; Charlie’s destination unit was consumed by the completed work order. Fleet availability remained 4/10 (40%). The script records its API call list but does not capture an audit count. This is a workflow rehearsal against synthetic in-memory state, not an operational outcome.
- Cleanup removed 101 verified in-workspace targets (85 cache/temp directories and 16 logs). Two locked legacy logs remain under `backend/` (`.fd001-8006.stderr.log` and `.fd001-8006.stdout.log`) because Windows reported them in use; no process was stopped. Three locked native frontend binaries remain: `frontend/node_modules/@esbuild/.win32-x64-njLJvUZ3/esbuild.exe`, `frontend/node_modules/@esbuild/win32-x64/esbuild.exe`, and `frontend/node_modules/@rollup/rollup-win32-x64-msvc/rollup.win32-x64-msvc.node`. Generated `dist/` output was removed. These ignored/generated paths are excluded from the fresh tracked export.
- The backend full suite after the dependency-pin update passed in the main workspace (not the fresh export): from `backend/`, `python -m pytest tests -q --ignore=tests/test_api_compat.py` — 279 passed in 112.11s; `python -m tests.test_workflow` — 103 passed, 0 failed. The fresh export was separately used for the isolated dependency install, `pip check`, model load, frontend checks, startup, and API rehearsal. Its SciPy was 1.18.1; main-workspace SciPy was 1.18.0. The model artifact was not retrained or overwritten; it remains byte-identical at SHA-256 `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`. SHA-256 comparisons for all four NASA inputs also match the values recorded above. `git hash-object --path=<asset> <asset>` matched `git hash-object --no-filters <asset>` for each input and the model, confirming the checkout attributes do not rewrite their content. The demo script supports read-only preflight by default; its mutating path is explicitly guarded by `--allow-demo-mutations` and loopback-only validation, and never resets a running instance.

Final user-flow verification on the disposable export (no reset): the rehearsal completed the T-105 HP-204 inbound move and T-106 FP-102 move through Commander approval, Logistics receipt, and Base maintenance completion. WO-1046 completed and PM-002 resolved; A32 remained AT_RISK with the original synthetic FD001 RUL (65.43857 cycles), health 52, and unavailable failure probability. Fleet availability stayed 4/10 (40%). A post-completion UI/API read showed the linked event, work order, transfer, recommendation, and audit transitions. Screenshot evidence was captured by the reviewer outside the repository; it is not part of the package. The API rehearsal JSON records the exact requests and inventory before/after, but does not contain an audit count.

Changed files by task are listed in [final-polish-files.md](final-polish-files.md).
