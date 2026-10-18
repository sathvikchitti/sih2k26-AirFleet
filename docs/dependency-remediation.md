# Frontend dependency remediation

## Scope and result

This focused pass updates only the frontend's transitive selector parser and lockfile. The audit snapshot is from 2026-10-18 with Node `v24.8.0` and npm `11.6.0`. It does not establish whole-application security.

`postcss-selector-parser` moved from `6.1.4` to `7.1.6` using a root npm override. This removes the selector-parser advisory findings while preserving the installed Tailwind CSS 3 toolchain. Full frontend `npm audit --json` now reports five high package entries and no moderate entries: the direct `braces` finding and four parent metavulnerability entries (`chokidar`, `fast-glob`, `micromatch`, and `tailwindcss`) caused by the same braces advisory. `npm audit --omit=dev --json` reports zero findings. The remaining issue is development/build-time and does not affect the production dependency tree.

## Remaining audit entries

| Audit package entry | Installed | npm audit affected range | Dependency path | Phase | Root advisory |
| --- | --- | --- | --- | --- |
| `braces` | 3.0.3 | `<=3.0.3` | `tailwindcss → chokidar → braces`; also `tailwindcss → fast-glob → micromatch → braces` | dev/build | [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) |
| `chokidar` | 3.6.0 | `2.0.0 - 3.6.0` | `tailwindcss → chokidar → braces` | dev/build | same braces advisory, reported as an affected parent |
| `fast-glob` | 3.3.3 | `*` | `tailwindcss → fast-glob → micromatch → braces` | dev/build | same braces advisory, reported as an affected parent |
| `micromatch` | 4.0.8 | `>=0.2.0` | `tailwindcss → fast-glob → micromatch → braces` | dev/build | same braces advisory, reported as an affected parent |
| `tailwindcss` | 3.4.14 | `<=0.0.0-oxide-insiders.ff2c25f \|\| 2.1.0-canary.1 - 3.4.19` | direct development dependency; vulnerable paths are its `chokidar` and `fast-glob` dependencies | dev/build | same braces advisory, reported as an affected parent |

These are five npm audit package entries, not five distinct advisories. GHSA-vfj7-8cjw-p6xm identifies `braces` versions through `3.0.3` as affected and currently lists no patched version. npm suggests Tailwind CSS `4.3.3` as an automatic fix path; this is a major Tailwind upgrade and was not applied. The dependency chain is used by Tailwind's development-time content scanning. No arbitrary Tailwind or unrelated package upgrades were made.

The selector-parser advisory [GHSA-rj75-hqrm-r3gf](https://github.com/postcss/postcss-selector-parser/security/advisories/GHSA-rj75-hqrm-r3gf) affects versions `<7.1.6`; `7.1.6` is the patched version. The initial audit contained both a direct parser entry and a parent metavulnerability for `postcss-nested`. The parser entry was `postcss-selector-parser@6.1.4`; the parent remained `postcss-nested@6.2.0` through its declared parser dependency `^6.1.1`. Both paths are in the dev/build toolchain, with no production-runtime exposure.

| Resolved initial audit entry | Before → after | Initial advisory/audit range | Dependency path | Phase |
| --- | --- | --- | --- | --- |
| `postcss-selector-parser` | 6.1.4 → 7.1.6 | GHSA affected range `<7.1.6` | `tailwindcss → postcss-selector-parser`; also `tailwindcss → postcss-nested → postcss-selector-parser` | dev/build |
| `postcss-nested` (parent metavulnerability) | 6.2.0 → 6.2.0 | No independent advisory range; inherited from parser `<7.1.6` | `tailwindcss → postcss-nested → postcss-selector-parser` (nested declares parser `^6.1.1`) | dev/build |

Because `postcss-nested@6.2.0` declares parser `^6.1.1`, the override is a deliberate cross-major compatibility choice rather than a semver-compatible update. The isolated compatibility test below was completed before applying it. `npm ls` now reports both Tailwind and postcss-nested consumers resolved to `7.1.6`, with the override explicitly identified and no invalid-range result.

## Compatibility evidence

An isolated copy of the frontend was installed with the candidate root override before updating the project manifest. These outputs were compared against the current parser 6.1.4 build:

| Check | Parser 6.1.4 SHA-256 | Parser 7.1.6 SHA-256 | Result |
| --- | --- | --- | --- |
| Existing production CSS | `675CB32C0CF5DF5235AA9A92A2F0B85FB91974FC468E93B9C5420753F6710783` | same | Byte-identical |
| Tailwind variant fixture | `76196F5800AE625AC210D8B6B0DD9047339A0807A8ECE256E2AB4BC910C76C05` | same | Byte-identical |
| postcss-nested fixture | `244FF503F529C9BD393E4533503A3D87103922C8B3E42442256BFF59C1F4ECA4` | same | Byte-identical |

The Tailwind fixture exercised `group-hover`, `peer-checked`, `md:focus-visible`, and an arbitrary `data-[state=open]` variant. The nested fixture exercised `:is()`, a nested child selector, and an `@media` block. Tailwind's required `postcss-selector-parser/dist/util/unesc` subpath also resolved under 7.1.6. These focused checks support this project's current use; they are not a general compatibility guarantee for other parser consumers.

## Verification

From `E:\Projects\Air fleet\frontend`:

| Command | Result |
| --- | --- |
| `npm ls postcss-selector-parser --all` | Pass; Tailwind and postcss-nested resolve to 7.1.6; override is explicit. |
| `npm ci --ignore-scripts --dry-run` | Pass; lockfile is consistent. |
| `npm run build` | Pass; Vite 6.4.4 production build. |
| `npm run verify:views` | Pass; 19/19 views rendered. |
| `node --test scripts/prediction-contract.test.mjs` | Pass; 1/1 test. |
| `npm audit --json` | 5 high package entries, 0 moderate, 0 critical; all five stem from the braces advisory above. |
| `npm audit --omit=dev --json` | 0 findings in production dependencies. |

An isolated Vite 6.4.4 process was started on `127.0.0.1:5176` with `API_PROXY_TARGET=http://127.0.0.1:8007` and `VITE_API_BASE` unset, then stopped after read-only checks. The existing frontend processes on ports 5174 and 5175 and backend on 8007 were not restarted or modified for these probes.

| Probe | Result |
| --- | --- |
| Request with `Host: evil.example` | 403 |
| Origin `http://localhost:5175` | 200 with exact `Access-Control-Allow-Origin: http://localhost:5175` |
| Origin `http://localhost:5176` | 200, no `Access-Control-Allow-Origin` (CORS denial is in the response header, not an HTTP rejection) |
| Temporary dummy `.env` sentinel file | 403; the file was removed immediately, and its contents were not emitted |
| Proxied `GET /api/health` | 200 JSON |
| Compiled client bundle contains `API_PROXY_TARGET` or the proxy URL | No |

The backend owner separately ran from `E:\Projects\Air fleet\backend`:

```powershell
python -m pytest tests/test_fd001_provider.py tests/test_regressions.py tests/test_fd001_operations_scenario.py -q
```

That post-update run passed 47 tests in 28.91 seconds and emitted 59,997 scikit-learn warnings. The FD001 model artifact SHA-256 remained `14114389BC8DC09449CDE646F9B582933B58FFA188F3955508CC2F3E87D30BE9`. Earlier backend verification also reported 140 tests and a 103-check workflow harness. These backend results are handoff context, not frontend test coverage; the dependency change did not modify backend code or the model artifact.
