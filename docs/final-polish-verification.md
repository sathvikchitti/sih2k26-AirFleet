# Final polish verification

This record captures the requested final-push polish without implying that all requested tasks are complete. The entries below are limited to Task 1 implementation and the read-only initial investigation; later tasks require their own implementation and verification records.

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

## Initial read-only investigation for remaining tasks

No changes were made for Tasks 2–7 in this investigation. The production FD001 model SHA-256 is `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`.

- Task 2: `backend/app/domain/knowledge.py:113` currently maps engines 1–10 to `HP-204`. The only other catalog part categorized as Engine is `OE-310` (`backend/app/data.py:87–90`). The validated `FD001_ENGINE_PART_MAPPING` environment override is already present (`knowledge.py:116–155`); any alternating default remains a demo assumption, not an aircraft/engine identity fact.
- Task 3: the same read-only port-8011 probe returned no suggested moves at 30, 60, or 100 cycles. At 100 cycles, the API reported Alpha HP-204 expected demand `0.4707`, stock/free `0`, shortfall `1`; Bravo demand `1.5970`, quantity `1`, minimum reserve `1`, transferable `0`, shortfall `2`; Charlie demand `1.4431`, quantity/free `1`, forecast-protected `1`, shortfall `1`. Thus the current mapping concentrates every eligible forecast on HP-204; available Charlie stock is protected by its own expected demand, while Bravo's unit is at reserve. No suggested move is available without changing a synthetic input. This probe was from the pre-change running process; no fixture or mapping was altered.
- Task 5: risk thresholds are currently hard-coded in `backend/app/services/ml/base.py:69–88` (health-score bands `<45`, `<60`, `<80`; probability bands `>=0.70`, `>=0.45`, `>=0.25`). No risk-band policy GET endpoint was found. The README describes the values as demo policy thresholds, but current implementation does not expose them as configurable settings.
- Task 6: `GET /api/evaluation/summary` (`backend/app/routers/evaluation.py:12–33`) serves an aggregate synthetic scale-evaluation JSON, not the model metrics report. Official-test coverage values are in `backend/models/cmapss_fd001_rf_v1_metrics.json`; a UI coverage label would need an additive read-only projection or other agreed source. The README already labels the RF tree envelope uncalibrated.
- Task 7: the model artifact is 19,662,518 bytes. The requested runtime data set (`train_FD001.txt`, `test_FD001.txt`, `RUL_FD001.txt`) plus `readme.txt` totals 5,747,082 bytes; together they total 25,409,600 bytes (25.41 decimal MB, 24.23 MiB). `.gitignore` excludes the model `*.joblib` and the whole `CMAPSSData/` directory; the model-metrics JSON is not ignored. The current machine has Python 3.14.0 with NumPy 2.4.4, scikit-learn 1.9.0, and joblib 1.5.3 installed; FastAPI 0.136.1, uvicorn 0.46.0, and Pydantic 2.13.3 differ from the repo's pinned versions. The metrics record NumPy 2.4.4 and scikit-learn 1.9.0. `py -0p` reports no registered Python installations; a Python 3.13 WindowsApps alias exists but failed in this shell. `pip cache list numpy` reports no locally built wheels, `frontend/node_modules` exists, and npm's protected cache setting could not be queried. The Docker CLI is present, but `docker info` cannot connect to the Docker Desktop Linux engine pipe, so container build/run was unavailable. No fresh clone, archive, dependency installation, cleanup, or container operation was attempted during this read-only pass.

\n