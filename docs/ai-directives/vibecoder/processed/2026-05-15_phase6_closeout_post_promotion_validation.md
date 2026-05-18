Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: phase6-closeout-post-promotion-validation
Priority: high
Created: 2026-05-15
Status: pending
Target-Branch: product-dev-recovered
Target-Commit: f70cf332e507fee5ab5e11c09e0aa34de987b4a3
Validation-Scope: phase6-closeout-post-promotion-targeted
Allow-Code-Changes: false
Allow-Product-Push: false

# Phase 6 Closeout Post-Promotion Validation

## Objective

Validate the promoted `origin/product-dev-recovered` baseline after Phase 6 receivables closeout promotion.

This is a post-promotion verification gate. It must validate the product baseline itself, not the source feature branch.

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
- Do not run Docker rebuild unless the environment is blocked and CTO approves separately.
- Do not silently narrow or replace required commands.

## Required Setup Evidence

Leo must record:

- `git fetch origin --prune`
- explicit fetch of `product-dev-recovered`
- detached checkout of `origin/product-dev-recovered` or `FETCH_HEAD`
- `git rev-parse HEAD`
- confirmation that HEAD equals `f70cf332e507fee5ab5e11c09e0aa34de987b4a3`
- `git status --short` before validation
- Python version
- Poetry version
- PostgreSQL status and port mapping
- Redis status and port mapping, if relevant
- environment variables used, with secrets redacted

## Required Validation Commands

Run from the `backend` directory of the checked-out promoted product baseline.

1. Backend app import / route smoke:

```bash
REPORTING_USER_PASSWORD=<redacted> poetry run python -c "from main import app; print(len(app.routes))"
```

2. Receivables contract tests:

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

Use the correct Docker PostgreSQL host, port, database, user, and password for Lubuntu. Secrets must be redacted.

## Skip Policy

Leo must apply the `leo-headless-runner` DB-Capable Validation Skip Policy.

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
docs/ai-reports/lubuntu/2026-05-15_phase6_closeout_post_promotion_validation.md
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

- target commit is exactly `f70cf332e507fee5ab5e11c09e0aa34de987b4a3`
- no product/test code is changed
- no product branch is pushed
- required commands are all executed
- required tests have 0 failed
- DB schema contract has 0 skipped, or any skipped tests are explicitly justified as out of scope
- report is delivered to `origin/reports/lubuntu-validation`
