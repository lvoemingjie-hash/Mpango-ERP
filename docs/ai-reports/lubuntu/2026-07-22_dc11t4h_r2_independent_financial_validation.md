# DC-11T4H-R2 Independent Cross-Environment Financial Validation

Date: 2026-07-22
Reviewer: Codex
Verdict: `STOP_AND_REPORT_CTO`

## Scope And Target Proof

- Target branch: `origin/opencode/dc11t4h-receivable-collection-integrity-2026-07-22`
- Target commit: `c15100af551980706dc448065323cee5603b2993`
- Base branch: `origin/product-dev-recovered`
- Base commit: `303dc179e94527668f4f1d2145fab74be0f48751`
- Validation worktree HEAD: `c15100af551980706dc448065323cee5603b2993`
- HEAD/base ancestry proof: `git merge-base c15100af551980706dc448065323cee5603b2993 origin/product-dev-recovered` returned `303dc179e94527668f4f1d2145fab74be0f48751`
- Remote protected heads before report push:
  - `origin/product-dev-recovered` = `303dc179e94527668f4f1d2145fab74be0f48751`
  - `origin/platform-dev` = `12c5ee557876498240b1a36cc850d030d7bd8293`
- Report branch pre-push check: `git ls-remote --heads origin reports/dc11t4h-r2-independent-financial-validation-2026-07-22` returned no ref

## Changed-File Proof

`git diff --name-only 303dc179e94527668f4f1d2145fab74be0f48751..c15100af551980706dc448065323cee5603b2993` returned exactly these 21 files:

1. `ai-ledger/product-ai/2026-07-22_dc11t4h_receivable_collection_integrity.md`
2. `backend/alembic/versions/035_receivable_collection_integrity.py`
3. `backend/api/v1/orders.py`
4. `backend/models/binding.py`
5. `backend/repositories/payment_repository.py`
6. `backend/scripts/bootstrap_tenant_schema.py`
7. `backend/services/payment_service.py`
8. `backend/services/receivables_service.py`
9. `backend/tests/b6_hardening/test_b6_payment_atomicity.py`
10. `backend/tests/b6_hardening/test_b6_payments_api.py`
11. `backend/tests/test_dc11d_payment_replay_concurrency_integrity.py`
12. `backend/tests/test_dc11t4h_receivable_collection_integrity.py`
13. `backend/tests/test_payment_atomicity.py`
14. `backend/tests/test_payments_api.py`
15. `backend/tests/test_phase5_order_payment.py`
16. `backend/tests/test_receivables_service.py`
17. `backend/tests/test_u6f_onboarding_auth_chain_closeout.py`
18. `backend/tests/test_u6i1_owner_credential_setup_schema.py`
19. `frontend/src/components/ui/PaymentRecordModal.tsx`
20. `frontend/src/pages/orders/OrderListPage.tsx`
21. `frontend/src/tests/PaymentRecordModal.test.tsx`

`git diff --stat` summary: `21 files changed, 2270 insertions(+), 164 deletions(-)`.

Migration scope proof:

- `git diff --name-status ... -- backend/alembic/versions` showed only `A backend/alembic/versions/035_receivable_collection_integrity.py`
- No migration `<=034` changed

## Environment

- Disposable validation worktree: `/home/ivy/Desktop/dc11t4h-r2-worktree`
- PostgreSQL container version: `postgres (PostgreSQL) 16.14 (Debian 16.14-1.pgdg13+1)`
- Redis container version: `Redis server v=7.4.9`
- UTF-8 env set for backend commands: `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `LANG=C.UTF-8`, `LC_ALL=C.UTF-8`
- Disposable credentials were generated and used from a private env file; no credentials are reproduced here

## Backend Gates

### Alembic

Commands run:

1. `poetry env use $(which python3)`
2. `poetry install --no-interaction --with dev,test`
3. `.venv/bin/python -m alembic upgrade head`
4. `.venv/bin/python -m alembic current`
5. `.venv/bin/python -m alembic heads`
6. `.venv/bin/python -m alembic upgrade head` again for idempotent head re-run

Results:

- Initial upgrade to head completed successfully
- `alembic current` returned `035_receivable_collection_integrity (head)`
- `alembic heads` returned `035_receivable_collection_integrity (head)`
- Second `alembic upgrade head` exited `0` and left current revision unchanged

### Pytest

Long pytest runs were launched detached with `setsid + nohup` and polled via status files until completion.

1. Command:
   `./.venv/bin/python -m pytest tests/test_dc11t4h_receivable_collection_integrity.py -q`
   Result:
   `13 passed, 34 warnings in 10.07s`

2. Command:
   `./.venv/bin/python -m pytest tests/test_dc10k_finance_receivables_runtime.py tests/test_finance_receivables_api.py tests/test_receivables_service.py -q`
   Result:
   `40 passed, 80 warnings in 2.51s`

3. Command:
   `./.venv/bin/python -m pytest tests/test_phase5_order_payment.py tests/test_payment_atomicity.py tests/test_payments_api.py tests/b6_hardening/test_b6_payment_atomicity.py tests/b6_hardening/test_b6_payments_api.py tests/test_dc11d_payment_replay_concurrency_integrity.py tests/test_s5d5_payment_ledger_runtime_invariant.py tests/test_s5d6_multi_partial_payment_state_machine.py -q`
   Result:
   `81 passed, 1 xfailed, 179 warnings in 14.22s`

Backend gate summary:

- No test failures
- No test errors
- Totals across required backend commands: `134 passed, 1 xfailed`

## Financial Semantics Review

Actual code diff review and passing tests support the intended invariants:

- Ordinary cash/transfer settlement does not drive public `outstanding_balance` negative.
  Evidence:
  - `backend/services/payment_service.py` removed ordinary cash/transfer automatic negative receivable delta
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:113` `test_ordinary_cash_and_transfer_from_zero_binding_remain_zero`
- Ordinary unpaid orders remain visible in Finance even when binding `outstanding_balance` is zero.
  Evidence:
  - `backend/services/receivables_service.py` no longer filters zero-balance bindings out of the finance view
  - `backend/tests/test_receivables_service.py` passed in the required runtime/API suite
- Credit sale books full order total and closes order as paid.
  Evidence:
  - `backend/api/v1/orders.py` still applies positive receivable delta for `credit`
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:160` `test_credit_sale_partial_final_collection_and_finance_summary`
- Cash/transfer collection against an already-paid credit order reduces credit exposure without reopening the order.
  Evidence:
  - `backend/api/v1/orders.py` special-cases `current_state == PAID` when `credit_collection_exposure > 0`
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:160`
  - `frontend/src/tests/PaymentRecordModal.test.tsx:45` confirms paid credit orders stay in finance-collection mode rather than duplicate credit sale mode
- Partial and final collections create correct payment and ledger behavior.
  Evidence:
  - `backend/repositories/payment_repository.py` adds exposure computations
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:160`
  - `tests/test_s5d5_payment_ledger_runtime_invariant.py` and `tests/test_s5d6_multi_partial_payment_state_machine.py` both passed
- Idempotent replay does not duplicate collections or ledger entries.
  Evidence:
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:280` `test_credit_collection_idempotent_replay_has_no_duplicate_ledger`
  - `backend/tests/test_dc11d_payment_replay_concurrency_integrity.py` passed
- Over-collection fails without side effects.
  Evidence:
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:235` `test_over_collection_is_rejected_without_side_effects`
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:322` `test_concurrent_credit_collection_cannot_over_collect`
- Invalid historical settlement data makes migration `035` fail closed.
  Evidence:
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:830`
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:855`
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:874`
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:924`
- Legacy negative cash-derived balances reconcile to zero and the non-negative DB check is installed.
  Evidence:
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:976` `test_migration_repairs_legacy_negative_cash_balance_and_adds_check`
  - `backend/models/binding.py:19`
  - `backend/alembic/versions/035_receivable_collection_integrity.py:26`
  - `backend/scripts/bootstrap_tenant_schema.py:39`
- Cross-tenant receivables are isolated.
  Evidence:
  - `backend/tests/test_dc11t4h_receivable_collection_integrity.py:412` `test_credit_collections_are_isolated_across_tenants`

No financial mismatch, migration failure, HTTP 500 evidence, or failing financial test was observed in the required backend scope.

## Frontend Gates

Commands run:

1. `pnpm install --frozen-lockfile`
2. `pnpm exec vitest run src/tests/PaymentRecordModal.test.tsx`
3. `pnpm build`

Results:

- `pnpm install --frozen-lockfile`: passed
- `pnpm exec vitest run src/tests/PaymentRecordModal.test.tsx`: `1 passed test file`, `4 passed tests`
- `pnpm build`: passed

Frontend review evidence:

- `frontend/src/pages/orders/OrderListPage.tsx` keeps paid ordinary orders from exposing the order-list payment action
- `frontend/src/tests/PaymentRecordModal.test.tsx:45` verifies duplicate credit sale is disabled for paid credit orders
- `frontend/src/tests/PaymentRecordModal.test.tsx:64` verifies remaining collectible exposure is `credit minus later collections`
- `frontend/src/tests/PaymentRecordModal.test.tsx:109` verifies ordinary paid orders do not expose a remaining balance
- `frontend/src/pages/orders/OrderListPage.tsx` now fails closed on payment-history load errors instead of falling back to full-order collectible exposure

Observed frontend warnings:

- Vitest/build emitted a duplicate-key warning for `frontend/package.json` because `jsdom` appears twice
- Production build emitted a chunk-size warning for `dist/assets/index-684xuGQ2.js`

These warnings did not fail the requested frontend gates.

## Quality Gates

Passed:

- `python3 -m py_compile` on all changed Python files
- `git diff --check 303dc179e94527668f4f1d2145fab74be0f48751..c15100af551980706dc448065323cee5603b2993`
- `./backend/.venv/bin/pre-commit run --files <all 21 changed files>`
- Detect-secrets baseline proof from `.pre-commit-config.yaml`:
  `args: ['--baseline', '.secrets.baseline']`
- No source or lockfile changes were created by the validation steps

Scan note:

- ASCII/mojibake scan found non-ASCII long-dash characters in comments only, not mojibake, at:
  - `backend/tests/test_payment_atomicity.py:6732`
  - `backend/tests/test_phase5_order_payment.py:8038`
  - `backend/tests/test_phase5_order_payment.py:8041`
  - `backend/tests/test_phase5_order_payment.py:8042`
  - `backend/tests/test_phase5_order_payment.py:8361`
  - `backend/tests/test_phase5_order_payment.py:8372`
  - `backend/tests/test_phase5_order_payment.py:8647`
  - `backend/tests/test_phase5_order_payment.py:8783`
  - `backend/tests/test_phase5_order_payment.py:8793`
  - `backend/tests/test_phase5_order_payment.py:8829`
  - `backend/tests/test_phase5_order_payment.py:8866`

Blocking quality-gate failure:

- `npx gitnexus analyze` failed twice during package setup/runtime.
  Evidence from npm log `~/.npm/_logs/2026-07-22T05_41_18_659Z-debug-0.log`:
  - `gitnexus@1.6.9 postinstall { code: 1, signal: null }`
  - `onnxruntime-node@1.27.0 postinstall { code: 1, signal: null }`
  - npm exited `1`
- `npx gitnexus status` failed.
  First attempt evidence from npm log `~/.npm/_logs/2026-07-22T05_39_25_868Z-debug-0.log`:
  - `Error: spawn sh ENOENT`
  - `npm error code ENOENT`
  Second attempt with explicit `PATH` and `npm_config_script_shell=/bin/bash` still exited `1`, with latest npm log `~/.npm/_logs/2026-07-22T05_41_54_214Z-debug-0.log` ending at npm exit `1`

Because `gitnexus analyze` and `gitnexus status` are explicitly required quality gates and did not complete successfully, I cannot issue `PASS_FOR_CTO_DC11T4H_MERGE_REVIEW`.

## Findings

- P1: Required quality gate failure. `npx gitnexus analyze` and `npx gitnexus status` both failed in this environment, so the requested gate set is incomplete and the review must stop short of PASS.
- P3: Non-ASCII punctuation exists in changed backend test comments. This is not mojibake and did not affect behavior, but it is a minor hygiene finding from the requested ASCII scan.

## Cleanup And Push Proof

Pending final report-branch push and post-push teardown steps:

- Remove disposable PostgreSQL and Redis containers
- Remove disposable volumes
- Remove backend `.venv`
- Remove temporary state files
- Confirm report branch push only
- Confirm validation worktree clean after report commit

This section will be updated in the final pushed report commit with concrete command results.
