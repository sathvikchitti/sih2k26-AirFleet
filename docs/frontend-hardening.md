# Frontend development-server hardening

## Scope

This change hardens the local Vite development server and updates the frontend build toolchain. It does not establish whole-application security, authenticate demo roles, or authorize API reads. The Vite checks below cover one isolated local dev-server instance only.

## Dependency versions and advisory review

The frontend now pins Vite `6.4.4`, `@vitejs/plugin-react` `4.3.4`, and PostCSS `8.5.30`. React and the other CSS tooling versions were left unchanged. The plugin's published peer range includes Vite 6; the installed Autoprefixer, Tailwind CSS, and Vite package ranges accept PostCSS 8.5.30. The workspace Node runtime was `v24.8.0` (npm `11.6.0`).

Vite `5.4.10` was within the affected range for the development-server CORS/WebSocket origin advisory, which also applies to local-only servers. Vite 6.4.4 is past the patched versions for the reviewed Vite advisories, including the Windows path-deny bypass and the October 2026 path and middleware advisories:

- [GHSA-vg6x-rcgg-rjx6: dev-server cross-origin request/response access](https://github.com/vitejs/vite/security/advisories/GHSA-vg6x-rcgg-rjx6)
- [GHSA-93m4-6634-74q7: Windows backslash path-deny bypass](https://github.com/vitejs/vite/security/advisories/GHSA-93m4-6634-74q7)
- [GHSA-fx2h-pf6j-xcff: Windows alternate-path deny bypass](https://github.com/vitejs/vite/security/advisories/GHSA-fx2h-pf6j-xcff)
- [GHSA-rq7h-c2jc-7f22: files outside `server.fs.allow`](https://github.com/vitejs/vite/security/advisories/GHSA-rq7h-c2jc-7f22)
- [GHSA-9jrq-w75r-8gcw: cross-origin execution through custom middleware](https://github.com/vitejs/vite/security/advisories/GHSA-9jrq-w75r-8gcw)
- [Vite 6.4.4 package metadata](https://github.com/vitejs/vite/blob/v6.4.4/packages/vite/package.json)
- [React plugin 4.3.4 package metadata](https://github.com/vitejs/vite-plugin-react/blob/v4.3.4/packages/plugin-react/package.json) and [changelog](https://github.com/vitejs/vite-plugin-react/blob/v4.3.4/packages/plugin-react/CHANGELOG.md)

PostCSS 8.5.30 is beyond the patched versions in the reviewed advisories for stringification XSS, source-map reads, and source-map path traversal:

- [GHSA-qx2v-qp2m-jg93](https://github.com/postcss/postcss/security/advisories/GHSA-qx2v-qp2m-jg93)
- [GHSA-6g55-p6wh-862q](https://github.com/postcss/postcss/security/advisories/GHSA-6g55-p6wh-862q)
- [GHSA-fxqj-rqcc-2cmp](https://github.com/postcss/postcss/security/advisories/GHSA-fxqj-rqcc-2cmp)
- [GHSA-r28c-9q8g-f849](https://github.com/postcss/postcss/security/advisories/GHSA-r28c-9q8g-f849)
- [PostCSS 8.5.30 package metadata](https://github.com/postcss/postcss/blob/8.5.30/package.json)

At the time this initial hardening report was written, `npm audit` had 7 package findings (5 high and 2 moderate). A subsequent focused parser remediation removed both moderate entries. The current audit has 5 high package entries (all metavulnerable through the single braces advisory); see the detailed, current [dependency remediation report](dependency-remediation.md). The initial 7-entry count is historical, not the current result. The audit still offers Tailwind CSS `4.3.3` as a fix path for several entries, which is a major upgrade and was not included. The report did not list Vite, the React Vite plugin, or PostCSS 8.5.30 as vulnerable.

## Local configuration

`frontend/vite.config.js` binds the dev and preview servers to `127.0.0.1`; the dev server uses strict port selection, `allowedHosts: ['localhost', '127.0.0.1']`, and explicit CORS origins for `localhost` and `127.0.0.1` on ports 5173, 5174, and 5175. CORS requests from other origins may still receive an HTTP response, but they do not receive an `Access-Control-Allow-Origin` permission.

The proxy target is configured server-side as `API_PROXY_TARGET`, defaulting to `http://127.0.0.1:8002`. The previous `VITE_API_PROXY_TARGET` name is intentionally unsupported; it was a `VITE_`-prefixed value and therefore inappropriate for a server-only setting. `VITE_API_BASE` remains supported as an optional browser-visible API URL. It is public configuration and must not contain credentials. The sanitized [frontend/.env.example](../frontend/.env.example) documents both variables. Root and frontend `.gitignore` rules exclude `.env` and `.env.*` while allowing sanitized `*.example` files.

## Verification

Commands were run from `E:\Projects\Air fleet\frontend` with Node `v24.8.0`:

| Command | Result |
| --- | --- |
| `npm run build` | Pass; Vite 6.4.4 production build completed. |
| `npm run verify:views` | Pass; 19/19 views rendered. |
| `node --test scripts/prediction-contract.test.mjs` | Pass; 1/1 test. |
| `npm audit --json` | Historical initial report: 7 package findings. Current result is in [dependency-remediation.md](dependency-remediation.md). |

An isolated Vite process ran at `http://127.0.0.1:5175/` with `API_PROXY_TARGET=http://127.0.0.1:8002`. Read-only probes returned:

| Probe | Result |
| --- | --- |
| UI `/` | 200 |
| Proxied `/api/health` | 200 |
| CORS preflight from `http://localhost:5175` | 204 with `Access-Control-Allow-Origin: http://localhost:5175` |
| CORS preflight from `https://evil.example` | 204 with no `Access-Control-Allow-Origin` |
| Request with `Host: evil.example` | 403 |
| `/.env.example?raw` | 403 |
| `/.env.example::$DATA?raw` (Windows alternate path form) | 403 |

For the final Stage 6 handoff, the isolated :5175 process was deliberately restarted after verifying its previous listener PID (`42576`) belonged to the frontend process launched for this task. The new Vite process was started with `API_PROXY_TARGET=http://127.0.0.1:8007` and `VITE_API_BASE` unset. The `npm` wrapper PID was `14856`; the new :5175 listener PID was `19708`; Vite 6.4.4 logged ready on `127.0.0.1:5175`.

Proxy identity was verified with read-only `GET /api/audit`: direct :8007 returned 12 rows, and the response through :5175 was byte-identical (SHA-256 `982544765F31BFDAC5C6425B5EAB0BCCB0604F96697460041EA68840A4A4B906` for both). The :8002 baseline had 13 rows. An A21 maintenance-timeline request returned zero work orders on both backends at the time of the final check, so that route was not used as identity proof. No mutation request was sent during these checks.

The existing :5174 runtime was not restarted or stopped and continued using the tooling already loaded in that process. The checks above exercise only the new isolated :5175 process and do not claim that the existing runtime was upgraded or that the complete application is secure.
