# DC-11D Payment Replay + Concurrency Financial Integrity

Branch: `kilo/dc11d-payment-replay-concurrency-integrity-2026-07-14`

Base: `origin/product-dev-recovered @ cb1b1fffc63ed19e320701043eed38b8f2bea0c7`

Verdict: `PASS_FOR_CTO_DC11D_R1_MERGE_REVIEW`

## Scope

- Removed legacy empty-body/state-only behavior from `POST /api/v1/orders/{order_id}/pay`.
- Required structured body, canonical payment method, positive amount, and validated `X-Idempotency-Key`.
- Reused existing tenant-local `payments.idempotency_key` column/index; no migration added.
- Added order row locking before prior payment reads, remaining balance calculation, target-state selection, and payment writes.
- Kept payment insert, receivable adjustment, order transition, and ledger posting on one tenant session transaction.
- Added same financial result replay, idempotency conflict, duplicate transfer reference, overpay concurrency, rollback, empty-body, and cross-tenant isolation coverage.
- Updated frontend payment modal/service to send `X-Idempotency-Key` only as a header.
- DC-11D-R1 removed unsupported payment-note UI/type payloads and rejects backend notes with `PAYMENT_NOTES_UNSUPPORTED` until persistence is explicitly designed.

## Impact

- GitNexus query/context/impact were run before symbol edits.
- `PayOrderRequest` was reported CRITICAL because payment/order tests import it directly.
- DC-11D-R1 `PayOrderRequest` impact was CRITICAL: 59 impacted, 52 direct dependents; direct dependents were API/tests/importers including S5D4B, S5A, Phase5, DC11D, DC10F, S5D5, and S5D6 payment tests.
- DC-11D-R1 API `pay_order` was ambiguous in `gitnexus impact`; `gitnexus context pay_order` identified `Function:backend/api/v1/orders.py:pay_order`, and `gitnexus cypher` listed direct dependents in S5D4B, S5A, DC11D, Phase5, DC10F, S5D5, S5D6, and business invariant tests.
- DC-11D-R1 frontend `PaymentRecordModal` impact was LOW with no direct dependents reported; `PayOrderData` impact was LOW with direct importers in dashboard/order pages and the payment modal.
- The impact remained inside expected payment/order/ledger/frontend payment paths.
- No HIGH/CRITICAL impact escaped expected payment/auth/platform paths.
- `gitnexus_detect_changes(scope: "staged")` was requested by project instructions but is not exposed in this runtime's MCP tool list and is not available as a GitNexus CLI command.
- Available GitNexus CLI staged-scope substitute checks were run with `impact` and `status`; staged files remained inside the DC-11D payment/order/frontend payment/report scope.
- DC-11D-R1 exact pre-commit limitation: `npx gitnexus detect-changes --scope staged` returned `error: unknown command 'detect-changes'`.
- DC-11D-R1 fallback compare was run against `cb1b1fffc63ed19e320701043eed38b8f2bea0c7`; staged R1 changes against `HEAD` were limited to the 9 allowed R1 files.

## Migration Decision

- No schema gap was proven.
- Existing `payments.idempotency_key` and tenant-local unique index are sufficient.
- Payment notes are not persisted in the MVP contract; no migration was added.
- Migrations `005`, `006`, `032`, and `033` were not edited.
- Migration `034` remains untouched for DC-11P1.
- Alembic head remained exactly `033_order_status_enum_reconciliation`.

## Validation Evidence

### DC-11D-R1

- RED reproduction after disposable DB schema initialization: `poetry run pytest tests/test_s5d4b_settled_cash_payment.py -q` produced 9 failed, 3 passed.
- RED failures covered missing idempotency keys in structured direct/API payment tests, legacy empty-body contract drift, and route rollback path blocked by missing idempotency header.
- `poetry run pytest tests/test_dc11d_payment_replay_concurrency_integrity.py -q`: 10 passed.
- `poetry run pytest tests/test_s5d4b_settled_cash_payment.py -q`: 12 passed.
- `poetry run pytest tests/test_s5a_fresh_tenant_real_user_journey_gate.py -q`: 3 passed.
- `poetry run pytest tests/test_phase5_order_payment.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d6_multi_partial_payment_state_machine.py tests/test_dc10f_payment_method_integrity.py -q`: 64 passed, 1 xfailed.
- `poetry run pytest tests/test_route_authorization_policy.py tests/test_auth_regressions.py -q`: 37 passed.
- `pnpm exec vitest run src/tests/PaymentRecordModal.test.tsx`: 1 passed.
- `pnpm build`: passed.
- `poetry run alembic heads`: `033_order_status_enum_reconciliation (head)`.
- `poetry run python -m py_compile ...`: passed for changed backend route/schema/tests.
- Unknown downstream `IntegrityError` now re-raises as `IntegrityError` after rollback when no idempotency-key or transfer-reference record exists; it is no longer mislabeled as `IDEMPOTENCY_KEY_CONFLICT`.
- The unknown `IntegrityError` regression proves payment rows, order status, outstanding balance, and ledger rows remain unchanged after rollback.
- Same financial result replay is the MVP contract: replay guarantees the same `payment_id`, amount, and method; the response status reflects current order status; no additional financial write occurs.

### DC-11D Original

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
