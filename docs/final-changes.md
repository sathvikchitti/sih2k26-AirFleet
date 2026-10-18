# Final push verification record

## Phase 1: reproducible FD001 demo launch

- Backend: `python -m pytest tests -q --ignore=tests/test_api_compat.py` — 207 passed.
- Frontend: `npm run build` — passed (53 modules); `npm run verify:views` — 19/19; `node --test scripts/prediction-contract.test.mjs` — 1/1.
- Launch smoke: `run_demo.ps1 -BackendPort 8011 -FrontendPort 5179` started the FD001 operations demo; frontend returned HTTP 200, the same-origin `/api/aircraft` proxy returned 10 aircraft, and A21 reported CRITICAL risk with RUL in cycles and `failure_probability: null`. Ctrl+C stopped the launcher-owned processes; the isolated ports were no longer listening afterward.
- Configuration: PowerShell script AST parse, Bash `-n`, PyYAML Compose parse, and `docker compose config --quiet` passed. `git diff --check` passed.
- Docker image build was not run: Docker CLI is installed, but the Docker Desktop Linux engine is unavailable (`docker info` cannot connect to its named pipe). No Docker installation or startup was attempted.
- Existing trained model artifact SHA-256: `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9` (unchanged; launchers do not retrain).
