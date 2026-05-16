Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: mvp-sprint-a-finance-receivables-validation
Priority: high
Created: 2026-05-16
Status: pending
Target-Branch: codex/mvp-sprint-credit-loop-2026-05-15
Target-Commit: c20fa71cc3921137faed047b454e627182f54ee9
Validation-Scope: mvp-sprint-a-finance-receivables-ui-targeted
Allow-Code-Changes: false
Allow-Product-Push: false

# MVP Sprint A Finance Receivables UI Validation

## Objective

Validate the MVP Sprint A feature branch in the Lubuntu environment.

This branch adds the wholesaler-facing Accounts Receivable UI slice and related frontend contract mapping for existing Phase 6.2/6.3A receivables endpoints.

## Execution Path

GitHub Actions -> runner ivy-20149 -> run_directive.sh v2 -> Leo headless executor.

Vibecoder chat agent must not execute this validation path.

## Forbidden Actions

- Do not modify product code.
- Do not modify test code.
- Do not push `product-dev-recovered`.
- Do not push `main`.
- Do not push `platform-dev`.
- Do not merge.
- Do not run `git reset --hard`.
- Do not run full pytest.
- Do not run dependency install unless required dependencies are missing and the report records the reason.
- Do not silently narrow or replace required commands.

## Required Setup Evidence

Leo must record:

- `git fetch origin --prune`
- explicit fetch of `codex/mvp-sprint-credit-loop-2026-05-15`
- detached checkout of the target branch or `FETCH_HEAD`
- `git rev-parse HEAD`
- confirmation that HEAD equals `c20fa71cc3921137faed047b454e627182f54ee9`
- `git status --short` before validation
- Node version
- pnpm version
- Python version
- Poetry version
- PostgreSQL status and port mapping if DB-capable tests are attempted
- Redis status and port mapping if relevant
- environment variables used, with secrets redacted

If branch checkout fails, do not report "branch missing" until `git ls-remote --heads origin codex/mvp-sprint-credit-loop-2026-05-15` has been recorded.

## Required Validation Commands

Run frontend commands from the `frontend` directory of the checked-out target branch.

1. Frontend build:

```bash
pnpm run build
```

2. Frontend lint:

```bash
pnpm run lint
```

Run backend commands from the `backend` directory of the checked-out target branch.

3. Receivables service/API targeted regression:

```bash
poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short
```

4. Phase 5/6 payment regression:

```bash
REPORTING_USER_PASSWORD=<redacted> poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

5. Optional DB schema contract with skip policy if PostgreSQL is available and already prepared:

```bash
DATABASE_URL=<redacted> TEST_DATABASE_URL=<redacted> poetry run pytest tests/test_payments_schema_contract.py -q -rs --tb=short
```

Do not run full pytest.

## Skip Policy

Leo must apply the `leo-headless-runner` DB-Capable Validation Skip Policy.

If any DB-capable / live DB / schema / migration test has `skipped > 0`:

- collect skip reasons using `-rs`
- do not report plain PASS for that DB-capable section
- downgrade to `PARTIAL_PASS_WITH_DB_EVIDENCE_GAP` or `BLOCKED_ENVIRONMENT`, unless the report proves the skip is intentional and not in scope
- never write "DB-capable PASS" without explaining skipped tests

Frontend and mocked/unit backend suites must still report exact pass/fail/xfailed/skipped counts.

## Report Requirements

Write report to:

```text
docs/ai-reports/lubuntu/2026-05-16_mvp_sprint_a_finance_receivables_validation.md
```

Report must include:

- GitHub Actions run URL
- runner name and id
- Leo invocation command
- whether Vibecoder chat agent was invoked
- branch and exact commit tested
- exact validation commands
- exact pass/fail/xfailed/skipped counts
- skipped count and skip reasons if any command skips tests
- original verdict before skip policy
- final verdict after skip policy
- git status before and after validation
- whether any product/test code changed
- whether any product branch was pushed
- whether dependency installation was needed

## Verdicts

Use one of:

- `PASS_FOR_CTO_REVIEW`
- `PARTIAL_PASS_WITH_DB_EVIDENCE_GAP`
- `BLOCKED_ENVIRONMENT`
- `FAIL_FOR_CTO_REVIEW`
- `INSUFFICIENT_EVIDENCE`

## Pass Criteria

This validation can be `PASS_FOR_CTO_REVIEW` only if:

- target commit is exactly `c20fa71cc3921137faed047b454e627182f54ee9`
- no product/test code is changed
- no product branch is pushed
- required commands 1-4 are all executed
- frontend build and lint pass
- backend required targeted tests have 0 failed
- any optional DB schema contract run follows skip policy
- report is delivered to `origin/reports/lubuntu-validation`
