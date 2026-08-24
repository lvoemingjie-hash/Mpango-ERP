# FROZEN REPORT — DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1

- Task: frozen forgot/reset Playwright harness implementation (harness only).
- Parent: `8c462170804322d3f73803d8991c00879582e232`
  (DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2: U6I2 token row identity determinism closure)
- Branch: `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-forgot-reset-playwright-harness-2026-08-24`
- Candidate SHA: recorded in the commit itself and in the task report (a file
  cannot contain its own hash); `candidate^` MUST equal the parent above.
- Accepted evidence chain: protocol `132cf7edaac5d6c57ebcdc2465334f4aa465aab2`,
  Kilo source review `4d42ffcae09d3a362f778c1e0661a72e1147dcba`,
  Lubuntu zero-red `5570093ec7f9e3dc2b4083ac8c091aae75a62d1d`.

## Mode compliance

Harness implemented and frozen ONLY. No product runtime was started (no
backend / frontend / PG / Redis), the authoritative browser journey was NOT
executed, no product source was modified, nothing merged or deployed. The
only executions were `pnpm install --frozen-lockfile` (harness deps in the
harness directory), `playwright test --list`, `tsc --noEmit`, and the pure
static validator.

## File manifest (this commit adds exactly this directory)

```
j1h2b-forgot-reset/.gitignore
j1h2b-forgot-reset/README.md
j1h2b-forgot-reset/FROZEN-REPORT.md
j1h2b-forgot-reset/package.json
j1h2b-forgot-reset/playwright.config.ts
j1h2b-forgot-reset/pnpm-lock.yaml
j1h2b-forgot-reset/tsconfig.json
j1h2b-forgot-reset/inventory/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_node_inventory.csv
j1h2b-forgot-reset/inventory/node-registry.json
j1h2b-forgot-reset/src/api-client.ts
j1h2b-forgot-reset/src/assertions.ts
j1h2b-forgot-reset/src/env.ts
j1h2b-forgot-reset/src/leak-scan.ts
j1h2b-forgot-reset/src/maildir.ts
j1h2b-forgot-reset/src/neutrality.ts
j1h2b-forgot-reset/src/reconciliation.ts
j1h2b-forgot-reset/src/token-store.ts
j1h2b-forgot-reset/src/ui-journey.ts
j1h2b-forgot-reset/tests/01-discover.spec.ts
j1h2b-forgot-reset/tests/02-neutrality.spec.ts
j1h2b-forgot-reset/tests/03-reset-entry.spec.ts
j1h2b-forgot-reset/tests/04-reset-submit.spec.ts
j1h2b-forgot-reset/tests/05-post-reset.spec.ts
j1h2b-forgot-reset/tests/06-multi-tenant.spec.ts
j1h2b-forgot-reset/tools/scan-artifacts.mjs
j1h2b-forgot-reset/tools/validate-static.mjs
```

`node_modules/` and `artifacts/` are gitignored and not committed.

## Inventory reconciliation — 24 / 5 / 29

- Inventory CSV: byte-identical copy of protocol blob
  `29a2bdd30b8ffd9142404dd530486d7fa6fd1f15` (9107 bytes), verified by
  `git hash-object` equality against
  `132cf7ed:docs/ai-reports/test-plans/2026-08-23_..._node_inventory.csv`.
- Strict parse: 30 lines (header + 29 rows), 15 columns per row,
  24 browser-authoritative + 5 non-browser.
- Browser 24 (== `playwright --list` titles, exact set, CSV order):
  F1-D, F1-T, F1-M, F2-D, F2-T, F2-M, F3, F4, F5, R1, R2, R3, R4, R5,
  R7-POLICY, R7-POLICY-M, R8, R8-M, R9, R10, R10-M, R11, R12, M1.
- Non-browser 5 (registry-accounted, NEVER browser PASS):
  F6 (PRECONDITION — maildir helper, in-memory only),
  R6 (BACKEND_PRE_GATE_ONLY), M2 (BACKEND_PRE_GATE_ONLY),
  R13 (POSTCOND — tools/scan-artifacts.mjs after the run),
  RT0 (PROTOCOL_BLOCKER — status BLOCKED_BY_H2_C; no API bypass of the
  missing retailer UI).

## Gate results (freeze-time)

| Gate | Result |
|---|---|
| `pnpm install --frozen-lockfile` (harness dir, PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1) | PASS — @playwright/test 1.49.1 / @types/node 22.10.5 / typescript 5.7.3, exact pins |
| `npx playwright test --list` | PASS — exactly 24 tests in 6 files, titles set-equal to the 24 browser inventory IDs, no duplicates/unregistered nodes |
| `node tools/validate-static.mjs` | PASS — 5/5 steps (CSV 29x15 + 24/5, registry cross-check, list set-equality, forbidden-marker scan + frozen config invariants, strict UTF-8/no-BOM/no-CR over all committed harness files) |
| `npx tsc --noEmit` | PASS — zero diagnostics |
| `git diff --check` | PASS (run at commit time) |
| detect-secrets | PASS (run at commit time; harness scan clean) |
| Product directories vs parent | byte-identical — the commit tree differs from 8c462170 ONLY by the added `j1h2b-forgot-reset/` directory (verified with `git diff --stat` at commit time) |

## Credential and token boundary proof

- All successful-auth credentials come from `J1H2B_*` env vars read at RUN
  time; `loadJourneyEnv` fails closed naming missing VARIABLE NAMES only.
  No credential value exists in any committed file, log line or artifact name.
- The maildir reset link/token is read by `src/maildir.ts` into memory only;
  it is never written to disk, never logged, never captured by trace/
  screenshot/video (all disabled in the frozen config).
- F3/F4/F5 keep only `(status, sha256(body), bodyLength)`; the raw response
  body is discarded at capture time.
- All secret-adjacent assertions go through `assertSan` with field-level
  messages; R12/R13 findings are `surface:field` pairs with values withheld.

## Verdict

`STOP_AND_REPORT_CTO_AWAITING_KILO_HARNESS_REVIEW_AND_BROWSER_EXECUTION`

The only next step after this freeze is the Kilo harness source/authenticity
review. The authoritative browser journey is NOT run by this task.
