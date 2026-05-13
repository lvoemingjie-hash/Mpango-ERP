# Phase 6 Credit Payment Ledger Semantics Promotion

Date: 2026-05-13
Executor: Claude Code under CTO supervision
CTO Review: corrected after CTO rerun of Windows mock suite
Verdict: READY_FOR_CTO_REVIEW

## Scope

Promote Phase 6 credit payment ledger semantics from the Phase 6 feature branch
into the recovered product baseline.

## Branches and Commits

- Product base branch: origin/product-dev-recovered
- Product base commit: 030e96449ea9e09559fb777cfb62b8d66a08d92a
- Phase 6 source branch: origin/codex/phase6-credit-payment-mvp-2026-05-13
- Phase 6 source commit: e132dc640b9ee4dd85b015d0284d256d73cdc486
- Promotion worktree: C:\Users\Jeff0\MPANGO ERP\phase6-promotion-2026-05-13

## Merge Result

The promotion worktree was created outside the dirty main workspace.

Merge result:

- Clean fast-forward from 030e964 to e132dc6
- No merge conflicts
- No product branch push
- No history rewrite
- No destructive git operation

Files promoted by the Phase 6 source branch:

- backend/api/v1/orders.py
- backend/services/order_service.py
- backend/tests/test_phase5_order_payment.py
- backend/tests/test_s5_ledger.py
- docs/ai/PROJECT.md
- ai-ledger/product-ai/2026-05-13_phase6_credit_ledger_semantics_fix.md
- ai-ledger/product-ai/2026-05-13_phase6_credit_payment_mvp_acceptance.md

## Validation Evidence

### Windows mock and route-level suite

Claude first ran:

```bash
poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

Initial result:

- 50 passed
- 3 failed
- 1 xfailed

The 3 failures were caused by missing `REPORTING_USER_PASSWORD`, not by Phase 6
business logic. CTO reran the same suite after setting the required reporting
database credential in the shell with a redacted test value:

```powershell
$env:PYTHONIOENCODING='utf-8'
poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

Corrected result:

- 53 passed
- 1 xfailed
- 0 failed
- 48 warnings

This is the promotion evidence for `tests/test_phase5_order_payment.py`.

### Lubuntu DB-capable ledger suite

Windows did not run the real DB ledger suite. DB-capable evidence comes from
Vibecoder on Lubuntu:

- Report branch: origin/reports/lubuntu-validation
- Evidence commit: 8bf0afeac7ddf1d1ab9b355947497636b16df9b7
- Report path: docs/ai-reports/lubuntu/2026-05-13_lubuntu_phase6_credit_ledger_semantics_validation.md
- Result: tests/test_s5_ledger.py = 15 passed

The Lubuntu retry explicitly set `POSTGRES_HOST=localhost` after the first run
was blocked by DNS resolution of the Docker Compose service name `postgres`.

## CTO Assessment

The Phase 6 fix closes a financial semantics defect: credit payments can mark
an order as paid while preserving receivable-ledger semantics instead of
posting a cash settlement ledger entry.

Risk assessment:

- Code logic risk: LOW after 53 passed, 1 xfailed in the Windows suite
- DB accounting risk: LOW after Lubuntu 15/15 S5 ledger pass
- Merge risk: LOW due clean fast-forward and no conflicts
- Promotion execution risk: still requires CTO approval before push

## Current Promotion State

Claude created a local promotion commit:

- Commit: 7b8dcaa4313d5783f2196f161771d9ae5e0b321c
- Message: promote(phase6): Phase 6 credit payment ledger semantics promotion
- Push status: not pushed

This ledger was then corrected by CTO review to preserve the accurate test
result and remove misleading environment-failure framing.

## Final Verdict

READY_FOR_CTO_REVIEW.

The promotion is ready for CTO push decision after this corrected ledger is
committed in the promotion worktree.
