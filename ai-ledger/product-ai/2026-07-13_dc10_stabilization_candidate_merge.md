# DC-10 Stabilization Candidate Merge

Date: 2026-07-13

## Objective

Build and validate one controlled product candidate containing the approved
DC-10E, DC-10F, and DC-10G fixes before promotion to
`product-dev-recovered`.

## Baseline

- Protected branch: `origin/product-dev-recovered`
- Verified baseline: `547b0b294aa387d6179f53eca3ec162532a1e29e`
- Candidate branch: `codex/dc10-stabilization-candidate-2026-07-13`
- Isolated worktree: `_dc10_stabilization_candidate_2026-07-13`
- `origin/platform-dev` was not modified or pushed.

## Approved Sources

### DC-10E export worker tenant context reconstruction

- Source commit: `743b8b07e2ab89696389860e54a4049bb303850a`
- Merge commit: `c9daca7e`
- Purpose: reconstruct tenant ID and tenant schema in the reporting worker
  session before export SQL executes.

### DC-10F payment method financial integrity

- Source commit: `5bccc1b25b3db44ad78d5e393cadc034c320c318`
- Merge commit: `be836d65`
- Purpose: restrict financially effective payment methods to `cash`,
  `transfer`, and `credit` at request, service, frontend, bootstrap, and
  database constraint boundaries.
- Alembic migration `032_payment_method_integrity` is forward-only and does
  not modify migration `005`.

### DC-10G platform UUID and export error hardening

- Source commit: `6514bbe34e7517bc466e58d8f30fbbdb6fb4105e`
- Merge commit: `db8669e0`
- Purpose: fail closed on malformed platform UUIDs before SQL and prevent raw
  export enqueue exception text from entering public responses or logs.

## Candidate-Only Test Stabilization

- Commit: `89ae2033`
- Production code changed: no
- Files:
  - `backend/tests/test_dc10g_platform_uuid_export_error_hardening.py`
  - `backend/tests/test_platform_p10_contracts.py`
  - `ai-ledger/product-ai/2026-07-13_dc10g_platform_uuid_export_error_hardening.md`

Integrated execution found that DC-10G tests using `asyncio.run()` cleared the
current loop on Python 3.12. Later P10 tests using
`asyncio.get_event_loop()` then failed by test order. The correction uses
pytest-managed async tests and direct `await`. The enqueue log assertion uses
`caplog` so logger capture is independent of import and handler order.

## Validation Environment

- Disposable PostgreSQL: `postgres:15-alpine`, local port `55439`
- Disposable container: `codex_dc10_candidate_pg`
- Test credentials were local placeholders and were not recorded.
- Backend and frontend commands ran serially from their respective project
  directories.

## Alembic Gate

- Fresh `poetry run alembic upgrade head`: PASS
- `poetry run alembic current`: `032_payment_method_integrity (head)`
- `poetry run alembic heads`: `032_payment_method_integrity (head)`
- Head count: exactly one

## Backend Integrated Gate

The combined gate covered:

- DC-10E export worker context tests
- S6 async export tests
- DC-10F payment method migration and API tests
- Phase 5 order/payment tests
- S5-D4B, S5-D5, and S5-D6 payment/ledger tests
- DC-10G platform UUID and export error tests
- Route authorization policy
- Platform P10 contracts, audit API, and stats API
- Auth regressions

Final result:

- `420 passed`
- `1 xfailed`
- `0 failed`
- `0 errors`

Pre-final failures were classified and corrected as test configuration or
test isolation issues:

- A weak test `SECRET_KEY` was rejected by the existing security gate.
- Reporting tests required an explicit disposable `REPORTING_DATABASE_URL`.
- `asyncio.run()` and legacy `get_event_loop()` usage caused order-dependent
  loop state.
- `capsys` did not reliably capture logger output in the integrated order.

No production defect was found in those failures.

## Frontend Gate

- `pnpm install --frozen-lockfile`: PASS; lockfile unchanged
- `pnpm exec vitest run`: `88 passed` across 12 files
- `pnpm build`: PASS; 1275 modules transformed

Known non-blocking warnings:

- Duplicate `jsdom` key in `frontend/package.json`
- Existing Vite chunk-size warning
- Existing React Router future-flag warnings
- Existing React test `act(...)` warnings

## Hygiene And Security

- `git diff --check`: PASS
- Scoped pre-commit: PASS
- Detect secrets: PASS
- No `.env`, credential, JWT, raw token, SMTP value, or database URL was
  committed or printed.

## GitNexus Gate

Pre-promotion indexing at merge tip `db8669e0` completed with:

- 12,780 nodes
- 39,082 edges
- 827 clusters
- 300 flows

The full compare against `origin/product-dev-recovered` was `CRITICAL`, with
19 changed files, 211 mapped symbols, and 20 affected flows. This rating is
expected because the candidate intentionally changes export worker context,
payment financial integrity, a forward migration, and platform API error
boundaries. It was not ignored: the combined backend, migration, frontend,
RBAC, platform, auth, payment, and ledger gates above cover the affected
critical paths.

The candidate-only unstaged test correction was `LOW`, with three changed
files and no affected execution flows.

## Promotion Decision

Verdict: `PASS_FOR_PRODUCT_PROMOTION`

Promotion is allowed only if:

1. `origin/product-dev-recovered` still equals the verified baseline
   `547b0b294aa387d6179f53eca3ec162532a1e29e` immediately before push.
2. The final candidate worktree is clean.
3. The candidate branch is pushed before the protected branch.
4. `origin/platform-dev` remains untouched.

After promotion, independent cross-environment validation and exact VPS
runtime validation remain mandatory before creating a replacement release
tag. The existing `release-2026-07-13` tag must not be moved.
