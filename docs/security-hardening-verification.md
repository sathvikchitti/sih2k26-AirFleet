# Final-day security hardening verification

Verified on 2026-10-20. Scope: evaluator access, deployment/reset defaults, focused regressions, and documentation. Existing uncommitted frontend design changes were preserved.

## Actual gaps identified before implementation

- Capability and base checks already existed, but `X-Demo-Role` and `X-Demo-Base` were unauthenticated caller claims. Hardened permission mode did not authenticate identity.
- Fleet, inventory, audit, model, and other read endpoints were public.
- Backend reset already defaulted off and required a Commander capability, but the Dockerfile, Compose, and both launchers enabled it automatically.
- CORS already used explicit local origins and disabled credentialed cross-origin access; the API proxy was server-side. Restricted hosting needed its own origin/default configuration.
- Provider error sanitization, loopback port binding, and launcher process ownership checks already existed and were retained.

## Files changed by this task

| File | Change |
| --- | --- |
| `backend/app/access.py` | Standard HTTP Basic gate; validated server-side account role/base assignments; discard incoming demo claims; browser-origin mutation guard; no-store responses. |
| `backend/app/main.py` | Install gate and validate configuration; use mode-specific CORS; add minimal `/livez` and authenticated `/login` redirect. |
| `backend/app/security.py` | Clarify relationship between authenticated assignments and local demo claims; preserve capability checks. |
| `backend/tests/test_evaluator_access.py` | 31 API security tests, including authenticated maintenance/transfer workflow. |
| `backend/tests/conftest.py` | Explicit local mode for the existing local-demo test fixtures; restricted tests override it. No existing assertions were removed or weakened. |
| `backend/Dockerfile` | Restricted access and reset-off defaults. |
| `docker-compose.yml` | Restricted access, backend-only credential environment, explicit origins, reset off, minimal liveness healthcheck. Existing loopback bindings retained. |
| `frontend/nginx.conf.template` | Forward `/login` for a browser Basic challenge and redirect; retain `/api/` proxy. |
| `run_demo.ps1` | Explicit local mode; refuse restricted-mode downgrade; reset opt-in via `-EnableReset`. |
| `run_demo.sh` | Explicit local mode; refuse restricted-mode downgrade; reset off unless explicitly configured. |
| `.dockerignore` | Exclude the local Python virtual environment from build context. |
| `README.md` | Exact local/restricted setup, backend secret format, HTTPS/IP restriction example, verification, reset behavior, and limitations. |
| `docs/security-hardening-verification.md` | This report. |

Disposable smoke helpers and logs are under ignored backend test/log paths; they contain no deployment credentials. Temporary Docker credentials were generated in memory and the isolated test containers/network were removed.

## Checks executed and actual results

| Check | Result |
| --- | --- |
| `python -u -m pytest tests -q --ignore=tests/test_api_compat.py --basetemp .pytest-tmp-hardening-full` from `backend/` | **310 passed**, including all 31 new evaluator-access tests, existing authorization/reset checks, model checks, and workflow regressions; 117.08 seconds. |
| `python -m tests.test_workflow` from `backend/` | **103 passed, 0 failed**. |
| Existing `tests/test_api_compat.py` against a disposable local-mode mock server | **61 passed, 0 failed**. Port 8000 was occupied, so the unchanged script was imported with its `BASE` set to free loopback port 8018. No process on port 8000 was stopped or mutated. |
| `npm ci --no-audit --no-fund` from `frontend/` | Passed with the existing lockfile; 183 packages installed. |
| `npm run build` from `frontend/` | Passed. |
| `npm run verify:views` from `frontend/` | Passed: **20/20 views rendered**, plus the existing evidence/policy/forecast rendering assertions. This is SSR verification, not interactive browser testing. |
| `scripts/demo_api_rehearsal.py --base-url http://127.0.0.1:5187 --allow-demo-mutations` via disposable Vite `/api` proxy to FD001 backend on 8017 | Passed all assertions for forecast transfer, Commander approval, receipt, triage, maintenance start/completion, inventory, model contract, and timeline. Reset was disabled. |
| `docker compose -p airfleet-security-check build` | Both Python 3.12 backend and frontend/Nginx images built successfully. |
| Disposable restricted Compose startup on loopback 8019/5189 | Passed health and application checks, then removed only the verification project's containers/network. |
| Real container HTTP tests, direct backend and frontend proxy | Unauthenticated fleet reads 401; authenticated reads 200; authenticated Commander reset 403; spoofed Commander role with Logistics credentials 403; untrusted browser-origin mutation 403; trusted CORS origin allowed and untrusted origin omitted. `/login` challenged and forwarded credentials, then redirected to frontend HTML. |
| Authenticated FD001 rehearsal through container Nginx `/api` | Passed the same 24-call end-to-end rehearsal using temporary server-bound Commander, Logistics, and Base Manager accounts. Completed WO-1046 and received T-105/T-106; model health signatures remained unchanged. |
| PowerShell parser for `run_demo.ps1`; `bash -n` on `run_demo.sh` in the built backend container | Passed. Launchers were syntax-checked; the smoke servers were started directly with equivalent local environment settings. |
| `git diff --check` | Passed; Git emitted only its configured PowerShell line-ending normalization notice. |
| Trained model and all four tracked NASA input files compared byte-for-byte with `HEAD` | All unchanged. Model SHA-256: `14114389bc8dc09449cde646f9b582933b58ffa188f3955508cc2f3e87d30be9`. |
| Frontend source/config scan for credentials | No embedded credential values found. Only the existing warning against putting secrets into browser-visible configuration matched. |

Sandboxed TestClient stalled on the first request and sandboxed npm failed; the successful verification runs used approved execution outside the sandbox. The first focused test attempts exposed two mistakes in new test expectations (an aircraft's base and the existing nested approval response), which were corrected before the passing full suite. The initial container Bash syntax attempt received Windows-translated CRLF through the helper's text pipe; passing raw source bytes fixed the helper without changing the Bash source.

## Hosting and remaining limits

Follow the README's **Evaluator access and deployment security** instructions: configure backend-only `DEMO_BASIC_USERS`, set the exact HTTPS `FRONTEND_ORIGINS`, run Compose with reset disabled, and expose only the frontend through an HTTPS reverse proxy restricted to evaluator IPs or a VPN. Visit `/login` before using the UI. Verify unauthenticated access, account role binding, and disabled reset from the deployed host before sharing access. No remote host was deployed or changed by this task.

The actual public TLS endpoint, certificate, edge IP/VPN restriction, and interactive browser credential prompt could not be verified because no hosted endpoint or evaluator network was supplied. The challenge/redirect/proxy transport was verified over loopback HTTP. Keep access private until the real HTTPS/edge checks pass.

Basic credentials are stored in the server environment, all authenticated evaluators may read all synthetic bases, and there is no MFA, application logout, password recovery, or application rate limiting. Static frontend assets include synthetic offline fixtures. Use unique random credentials, revoke them after the demo, keep one in-memory backend process, and restrict the entire frontend at the edge. State resets on process restart. These are documented limits of a time-limited proof of concept, not production or operational certification.
