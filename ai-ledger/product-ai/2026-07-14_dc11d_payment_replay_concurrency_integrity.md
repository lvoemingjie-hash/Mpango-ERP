# DC-11D Payment Replay + Concurrency Financial Integrity

Branch: `kilo/dc11d-payment-replay-concurrency-integrity-2026-07-14`

Base: `origin/product-dev-recovered @ cb1b1fffc63ed19e320701043eed38b8f2bea0c7`

Verdict: `PASS_FOR_CTO_DC11D_MERGE_REVIEW`

## Scope

- Removed legacy empty-body/state-only behavior from `POST /api/v1/orders/{order_id}/pay`.
- Required structured body, canonical payment method, positive amount, and validated `X-Idempotency-Key`.
- Reused existing tenant-local `payments.idempotency_key` column/index; no migration added.
- Added order row locking before prior payment reads, remaining balance calculation, target-state selection, and payment writes.
- Kept payment insert, receivable adjustment, order transition, and ledger posting on one tenant session transaction.
- Added exact replay, idempotency conflict, duplicate transfer reference, overpay concurrency, rollback, empty-body, and cross-tenant isolation coverage.
- Updated frontend payment modal/service to send `X-Idempotency-Key` only as a header.

## Impact

- GitNexus query/context/impact were run before symbol edits.
- `PayOrderRequest` was reported CRITICAL because payment/order tests import it directly.
- The impact remained inside expected payment/order/ledger/frontend payment paths.
- No HIGH/CRITICAL impact escaped expected payment/auth/platform paths.
- `gitnexus_detect_changes(scope: "staged")` was requested by project instructions but is not exposed in this runtime's MCP tool list and is not available as a GitNexus CLI command.
- Available GitNexus CLI staged-scope substitute checks were run with `impact` and `status`; staged files remained inside the DC-11D payment/order/frontend payment/report scope.

## Migration Decision

- No schema gap was proven.
- Existing `payments.idempotency_key` and tenant-local unique index are sufficient.
- Migrations `005`, `006`, `032`, and `033` were not edited.
- Alembic head remained exactly `033_order_status_enum_reconciliation`.

## Validation Evidence

- `poetry run pytest tests/test_dc11d_payment_replay_concurrency_integrity.py -q`: 8 passed.
- Backend validation bundle: 139 passed, 1 xfailed.
- Backend validation bundle included DC-11D, Phase5 payment, S5D5, S5D6, DC-10F, route authorization, and auth regressions.
- `pnpm exec vitest run src/tests/PaymentRecordModal.test.tsx`: 1 passed.
- `pnpm build`: passed.
- `poetry run alembic heads`: `033_order_status_enum_reconciliation (head)`.
- `poetry run python -m py_compile ...`: passed for changed backend files and tests.
- `git diff --check`: passed.
- Added diff lines ASCII scan: passed.
- Mojibake scan: passed.
- `detect-secrets scan` on changed files: results `{}`.

## Disposable Infrastructure

- Used disposable PostgreSQL container: `dc11d_d530800b_pg` on localhost port `63819`.
- Used disposable Redis container: `dc11d_d530800b_redis` on localhost port `63820`.
- No production credentials, real tokens, JWTs, customer emails, VPS access, deployment, or protected branch pushes were used.

## Notes

- `pre-commit run --all-files` hit a Windows GBK stdout encoding failure while hooks printed historical non-ASCII filenames and attempted to touch unrelated repository files.
- All unrelated hook modifications were restored.
- The intended DC-11D file set is validated with focused tests and scans.
