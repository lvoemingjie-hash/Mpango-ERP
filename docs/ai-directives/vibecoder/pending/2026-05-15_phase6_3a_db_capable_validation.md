Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: phase6-3a-db-capable-validation
Priority: high
Created: 2026-05-15
Status: pending
Target-Branch: codex/phase6-3a-receivables-contract-2026-05-14
Target-Commit: 5df6098f5a6f46bfb77a0ed6d03383d750446f9d
Validation-Scope: phase6-3a-receivables-contract-db-capable-targeted
Allow-Code-Changes: false
Allow-Product-Push: false

# Phase 6.3A DB-Capable Targeted Validation

## Objective

Validate the Phase 6.3A receivables API contract branch in the Lubuntu DB-capable environment using Leo headless execution.

This validation must verify that the typed receivables response contract remains stable and that the prior Phase 5/6 payment behavior is not regressed.

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
- Do not run Docker rebuild unless environment is blocked and CTO approves separately.
- Do not silently narrow or replace required commands.

## Required Setup Evidence

Leo must record:

- `git fetch origin --prune`
- explicit fetch of `codex/phase6-3a-receivables-contract-2026-05-14`
- detached checkout of the target branch or `FETCH_HEAD`
- `git rev-parse HEAD`
- confirmation that HEAD equals `5df6098f5a6f46bfb77a0ed6d03383d750446f9d`
- `git status --short` before validation
- Python version
- Poetry version
- PostgreSQL status and port mapping
- Redis status and port mapping, if relevant
- environment variables used, with secrets redacted

If branch checkout fails, do not report "branch missing" until `git ls-remote --heads origin codex/phase6-3a-receivables-contract-2026-05-14` has been recorded.

## Required Validation Commands

Run from the `backend` directory of the checked-out Phase 6.3A branch.

1. Backend app import / route smoke:

```bash
REPORTING_USER_PASSWORD=<redacted> poetry run python -c "from main import app; print(len(app.routes))"
```

2. Phase 6.3A receivables contract tests:

```bash
poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short
```

3. Phase 5/6 payment regression:

```bash
REPORTING_USER_PASSWORD=<redacted> poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

4. DB schema contract with skip policy:

```bash
DATABASE_URL=<redacted> TEST_DATABASE_URL=<redacted> poetry run pytest tests/test_payments_schema_contract.py -q -rs --tb=short
```

Use the correct Docker PostgreSQL host, port, database, user, and password for Lubuntu. Secrets must be redacted in the report.

## Skip Policy

Leo must apply the updated `leo-headless-runner` DB-Capable Validation Skip Policy.

If any DB-capable / live DB / schema / migration test has `skipped > 0`:

- collect skip reasons using `-rs`
- do not report plain PASS
- downgrade to `PARTIAL_PASS_WITH_DB_EVIDENCE_GAP` or `BLOCKED_ENVIRONMENT`, unless the report proves the skip is intentional and not in scope
- never write "DB-capable PASS" without explaining skipped tests

Ideal DB schema contract result:

```text
40 passed, 0 skipped, 0 failed
```

## Report Requirements

Write report to:

```text
docs/ai-reports/lubuntu/2026-05-15_phase6_3a_db_capable_validation.md
```

Report must include:

- GitHub Actions run URL
- runner name and id
- Leo invocation command
- whether Vibecoder chat agent was invoked
- branch and exact commit tested
- exact validation commands
- exact pass/fail/xfailed/skipped counts
- skipped count
- skip reasons collected: Yes/No
- any live DB tests skipped: Yes/No
- original verdict before skip policy
- final verdict after skip policy
- git status before and after validation
- whether any product/test code changed
- whether any product branch was pushed

## Verdicts

Use one of:

- `PASS_FOR_CTO_REVIEW`
- `PARTIAL_PASS_WITH_DB_EVIDENCE_GAP`
- `BLOCKED_ENVIRONMENT`
- `FAIL_FOR_CTO_REVIEW`
- `INSUFFICIENT_EVIDENCE`

## Pass Criteria

This validation can be `PASS_FOR_CTO_REVIEW` only if:

- target commit is exactly `5df6098f5a6f46bfb77a0ed6d03383d750446f9d`
- no product/test code is changed
- no product branch is pushed
- required commands are all executed
- required tests have 0 failed
- DB schema contract has 0 skipped, or any skipped tests are explicitly justified as out of scope
- report is delivered to `origin/reports/lubuntu-validation`
