# DC-12R1-S3-S2 Read-Only Retailer Payment and Finance Visibility

## Verdict

PASS_FOR_CTO_DC12R1_S3_S2_REVIEW

## Baseline And Branch

- Owner: KILO
- Baseline ref: origin/product-dev-recovered
- Baseline SHA: 44ec07ffd92c601957b78fb7909514360232e3eb
- Worktree: C:\Users\Jeff0\MPANGO ERP\_kilo_dc12r1_s3_s2_readonly_finance_2026-07-30
- Branch: kilo/dc12r1-s3-s2-read-only-retailer-finance-2026-07-30
- Delivery commit: final pushed HEAD for this report

## Baseline Gate

- Ran `git fetch --all --prune` before editing.
- Verified `git rev-parse origin/product-dev-recovered` returned `44ec07ffd92c601957b78fb7909514360232e3eb`.
- Created a clean isolated worktree from exact baseline `44ec07ffd92c601957b78fb7909514360232e3eb`.
- Verified `git merge-base --is-ancestor 44ec07ffd92c601957b78fb7909514360232e3eb HEAD` returned success in the isolated worktree.
- Initial isolated worktree status was clean on `kilo/dc12r1-s3-s2-read-only-retailer-finance-2026-07-30`.

## GitNexus Evidence

- Pre-edit `npx gitnexus analyze` completed successfully for the isolated baseline worktree.
- Pre-edit impact checks were run for `resolve_client_identity`, `configure_app`, `AppRouter`, `ClientLayout`, and existing S3-S1 route-inventory tests.
- Reported pre-edit impact level: LOW for all requested targets; no HIGH or CRITICAL impact was reported before edits.
- `npx gitnexus status` reported the index up to date at baseline commit `44ec07f`.
- `npx gitnexus analyze` reported `Already up to date` before staging.
- `npx gitnexus detect_changes --scope all` is not available in this installed CLI and returned `unknown command 'detect_changes'`; change-scope verification was completed with the available GitNexus impact/analyze/status evidence and direct git diff inspection.
- No shared payment-write, ledger, settlement, or receivable-mutation symbols were modified.

## Changed Files

- `backend/api/app.py`
- `backend/api/v1/client/finance.py`
- `backend/api/v1/client/payments.py`
- `backend/repositories/client_finance_repository.py`
- `backend/schemas/client.py`
- `backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py`
- `backend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py`
- `frontend/src/components/layout/ClientLayout.tsx`
- `frontend/src/pages/client/FinanceBalancePage.tsx`
- `frontend/src/pages/client/PaymentHistoryPage.tsx`
- `frontend/src/router/AppRouter.tsx`
- `frontend/src/services/clientFinanceService.ts`
- `frontend/src/tests/Dc12r1S3S2ClientFinance.test.tsx`
- `frontend/src/types/client.ts`
- `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2_read_only_retailer_finance.md`

## Backend Implementation

- Added isolated read-only client routes:
  - `GET /api/v1/client/payments`
  - `GET /api/v1/client/finance/balance`
- Both routes require `resolve_client_identity` and existing read permissions:
  - `client:payments:read`
  - `client:finance:read`
- Added `ClientFinanceRepository` as an isolated read-only repository for payment history and balance projections.
- Wired both routers in `configure_app`.
- Added retailer-safe schemas `ClientPaymentView` and `ClientFinanceBalanceView`.
- No migration `037` was added.
- No permission registry changes were made.

## Financial Boundary Proof

- Payment query joins `payments p` to `orders o` and enforces all authoritative predicates through one shared predicate list used by count and page queries:
  - `p.retailer_id = :retailer_id`
  - `o.retailer_id = :retailer_id`
  - `o.wholesaler_id = :wholesaler_id`
  - `p.is_deleted IS FALSE`
  - `o.is_deleted IS FALSE`
- Payment response exposes only `id`, `order_id`, `amount`, `method`, `status`, and `created_at`.
- Payment response does not expose `idempotency_key`, transaction IDs, supplier IDs, retailer IDs, audit fields, ledger rows, SQL details, or cross-supplier data.
- Payment filters are bounded and controlled: `page`, `size`, `order_id`, `method`, and `status` only.
- Invalid `order_id`, method, status, or malformed client identity returns controlled 400 responses before financial route-body SQL.
- Finance balance reads `public.wholesaler_retailer_bindings` by both `wholesaler_id` and `retailer_id`, with `status = 'active'` and `is_deleted IS FALSE`.
- Finance balance response exposes only `outstanding_balance`, `has_outstanding_balance`, and `updated_at`.
- `outstanding_balance` is read as the authoritative Decimal value; it is not clamped, inferred, or recomputed in frontend code.
- Negative balance values fail closed with sanitized `FINANCIAL_INTEGRITY_ERROR` handling.
- Frontend formatting converts strings only for display and performs no authoritative financial aggregation.
- `client:payments:create` remains future-gated and unused by registered client routes.
- Generic `/api/v1/payments` and `/api/v1/finance/...` routes remain denied to retailer tokens.

## RED Evidence

- Backend RED: `poetry run pytest tests/test_dc12r1_s3_s2_read_only_retailer_finance.py::TestReadOnlyClientFinanceRoutePolicy::test_exact_registered_client_route_inventory_is_11_and_get_only_financial_routes -q --tb=short` failed on baseline because registered client route inventory was 9 instead of required 11.
- Frontend RED: `pnpm vitest run src/tests/Dc12r1S3S2ClientFinance.test.tsx` failed on baseline because the new `clientFinanceService` and client finance pages were not present.

## GREEN Evidence

- Python compile: `poetry run python -m py_compile api/v1/client/payments.py api/v1/client/finance.py repositories/client_finance_repository.py schemas/client.py` passed.
- New S3-S2 suite natural order: `poetry run pytest tests/test_dc12r1_s3_s2_read_only_retailer_finance.py -q --tb=short` passed, 7 passed.
- New S3-S2 suite explicit reverse order: passed, 7 passed.
- Alembic validation: `alembic upgrade head`, `alembic current`, and `alembic heads` passed with sole head `036_retailer_mvp_identity (head)`.
- Required targeted regression set covering S3-S1, S2, H2, route-policy, RBAC, DC-11T4H, DC-10K, payment atomicity, replay, partial-payment, ledger, and receivables passed after isolating one invalid stale event-loop ordering artifact.
- Isolated rerun of `tests/test_u6i4_first_admin_rbac_creation.py` passed, classifying the targeted red artifact as harness-order residue rather than product behavior.

## Backend Full Runs

- Run A stack: fresh PG16 container `dc12r1_s3s2_pg_a` and Redis7 container `dc12r1_s3s2_redis_a`.
- Run A command: `poetry run pytest tests/ -q --tb=short` with zero exclusions.
- Run A result: `3030 passed, 48 skipped, 15 xfailed`, zero failed, zero errors.
- Run B stack: fresh PG16 container `dc12r1_s3s2_pg_b` and Redis7 container `dc12r1_s3s2_redis_b`.
- Run B command: `poetry run pytest tests/ -q --tb=short` with zero exclusions.
- Run B result: `3030 passed, 48 skipped, 15 xfailed`, zero failed, zero errors.
- A/B equality: identical pass/skip/xfail/fail/error totals.

## Frontend Results

- `pnpm install --frozen-lockfile` passed.
- `pnpm vitest run` passed: 16 test files, 147 tests.
- `pnpm build` passed.
- Nonblocking warnings observed: duplicate `jsdom` key in `package.json`, React Router future flags, existing React `act(...)` warnings, and Vite chunk size warning.

## Self-Review

- Confirmed every new financial SQL query uses both authoritative IDs where applicable.
- Confirmed no write SQL or mutating client payment/finance route was added.
- Confirmed no request-supplied `wholesaler_id` or `retailer_id` authority was added.
- Confirmed no money value is silently clamped or recomputed.
- Confirmed route allowlist was updated exactly to 11 registered client routes.
- Confirmed only intended files changed.
- `git diff --check` passed; only LF-to-CRLF working-copy warnings were emitted.
- Disposable validation containers were removed: target, Run A, and Run B PG/Redis containers.

## Cleanup Proof

- Removed `dc12r1_s3s2_pg_target`.
- Removed `dc12r1_s3s2_redis_target`.
- Removed `dc12r1_s3s2_pg_a`.
- Removed `dc12r1_s3s2_redis_a`.
- Removed `dc12r1_s3s2_pg_b`.
- Removed `dc12r1_s3s2_redis_b`.

## Final Status

- Verdict: PASS_FOR_CTO_DC12R1_S3_S2_REVIEW
- Protected branch push: none
- Tags: none
- Deployment: none
