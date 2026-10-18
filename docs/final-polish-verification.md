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

## Initial read-only investigation for Tasks 3–7

The initial inspection was read-only. The production FD001 model SHA-256 is `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`.

- Task 2 initial finding: before the change, `backend/app/domain/knowledge.py` mapped engines 1–10 to `HP-204`. Task 2 changes the default to odd engines `HP-204`, even engines `OE-310`. The only other catalog part categorized as Engine is `OE-310` (`backend/app/data.py:87–90`). The validated `FD001_ENGINE_PART_MAPPING` override remains (`knowledge.py`); both defaults and overrides are demo assumptions, not aircraft/engine identity facts.
- Task 3 initial finding: the pre-change read-only port-8011 probe returned no suggested moves at 30, 60, or 100 cycles. At 100 cycles, Alpha HP-204 expected demand was `0.4707`, stock/free `0`, shortfall `1`; Bravo demand `1.5970`, quantity `1`, minimum reserve `1`, transferable `0`, shortfall `2`; Charlie demand `1.4431`, quantity/free `1`, forecast-protected `1`, shortfall `1`. That was the all-HP-204 mapping and pre-change running process. After Task 2, the isolated 60-cycle probe described above found a feasible Charlie-to-Bravo HP-204 suggestion. These are different mapping snapshots; no fixture or inventory was altered.
- Task 5: risk thresholds are currently hard-coded in `backend/app/services/ml/base.py:69–88` (health-score bands `<45`, `<60`, `<80`; probability bands `>=0.70`, `>=0.45`, `>=0.25`). No risk-band policy GET endpoint was found. The README describes the values as demo policy thresholds, but current implementation does not expose them as configurable settings.
- Task 6: `GET /api/evaluation/summary` (`backend/app/routers/evaluation.py:12–33`) serves an aggregate synthetic scale-evaluation JSON, not the model metrics report. Official-test coverage values are in `backend/models/cmapss_fd001_rf_v1_metrics.json`; a UI coverage label would need an additive read-only projection or other agreed source. The README already labels the RF tree envelope uncalibrated.
- Task 7: the model artifact is 19,662,518 bytes. The requested runtime data set (`train_FD001.txt`, `test_FD001.txt`, `RUL_FD001.txt`) plus `readme.txt` totals 5,747,082 bytes; together they total 25,409,600 bytes (25.41 decimal MB, 24.23 MiB). `.gitignore` excludes the model `*.joblib` and the whole `CMAPSSData/` directory; the model-metrics JSON is not ignored. The current machine has Python 3.14.0 with NumPy 2.4.4, scikit-learn 1.9.0, and joblib 1.5.3 installed; FastAPI 0.136.1, uvicorn 0.46.0, and Pydantic 2.13.3 differ from the repo's pinned versions. The metrics record NumPy 2.4.4 and scikit-learn 1.9.0. `py -0p` reports no registered Python installations; a Python 3.13 WindowsApps alias exists but failed in this shell. `pip cache list numpy` reports no locally built wheels, `frontend/node_modules` exists, and npm's protected cache setting could not be queried. The Docker CLI is present, but `docker info` cannot connect to the Docker Desktop Linux engine pipe, so container build/run was unavailable. No fresh clone, archive, dependency installation, cleanup, or container operation was attempted during this read-only pass.

\n
