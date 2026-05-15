Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: phase6-closeout-schema-contract-rerun
Priority: high
Created: 2026-05-15
Status: pending
Target-Branch: product-dev-recovered
Target-Commit: f70cf332e507fee5ab5e11c09e0aa34de987b4a3
Validation-Scope: post-promotion-db-schema-contract-rerun
Allow-Code-Changes: false
Allow-Product-Push: false

# Phase 6 Closeout DB Schema Contract Rerun

## Objective

Resolve the post-promotion validation evidence gap caused by 19 skipped live DB schema contract tests.

Previous post-promotion validation confirmed:

- App smoke: passed, 106 routes.
- Receivables contract tests: 38 passed.
- Phase 5/6 payment regression: 53 passed, 1 xfailed.
- DB schema contract: 21 passed, 19 skipped.

The 19 skipped tests were caused by DB environment mismatch, not product code changes. This rerun must explicitly use the correct Docker PostgreSQL connection and prove whether DB schema contract reaches `40 passed, 0 skipped, 0 failed`.

## Execution Path

GitHub Actions -> runner ivy-20149 -> run_directive.sh v2 -> Leo headless executor.

Vibecoder chat agent must not execute this validation path.

## Forbidden Actions

- Do not modify product code.
- Do not modify test code.
- Do not edit tracked files.
- Do not push `product-dev-recovered`.
- Do not push `main`.
- Do not push `platform-dev`.
- Do not merge.
- Do not run `git reset --hard`.
- Do not run full pytest.
- Do not run Docker rebuild unless the environment is blocked and CTO approves separately.

## Required Setup Evidence

Leo must record:

- `git fetch origin --prune`
- explicit fetch of `product-dev-recovered`
- detached checkout of `origin/product-dev-recovered` or `FETCH_HEAD`
- `git rev-parse HEAD`
- confirmation that HEAD equals `f70cf332e507fee5ab5e11c09e0aa34de987b4a3`
- `git status --short` before validation
- Docker PostgreSQL container name, status, and port mapping
- actual DB connection string used, with password redacted
- whether a local `backend/.env.test` exists in the runner workspace
- if `backend/.env.test` exists, print only non-secret lines and redact passwords

## Required Command

Run from the `backend` directory of the checked-out promoted product baseline.

Use the actual Docker PostgreSQL mapping observed on runner:

- host: `127.0.0.1`
- port: `5432`
- database: `mpango_erp`
- user: `mpango`
- password: read from the running Docker container environment at execution time; do not write it to the report or to git

Command:

```bash
PGPASSWORD="$(docker exec mpango_postgres printenv POSTGRES_PASSWORD)" && \
DATABASE_URL="postgresql://mpango:${PGPASSWORD}@127.0.0.1:5432/mpango_erp" \
TEST_DATABASE_URL="postgresql://mpango:${PGPASSWORD}@127.0.0.1:5432/mpango_erp" \
poetry run pytest tests/test_payments_schema_contract.py -q -rs --tb=short
```

Secrets must be redacted in the report.

## Required DB Sanity Checks

Before pytest, run:

```bash
docker ps --filter name=mpango_postgres --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker exec mpango_postgres psql -U mpango -d mpango_erp -c "SELECT 1;"
docker exec mpango_postgres psql -U mpango -d mpango_erp -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='t_dev' AND table_name IN ('payments','retailer_prices') ORDER BY table_name;"
```

## Skip Policy

Leo must apply the `leo-headless-runner` DB-Capable Validation Skip Policy.

This rerun can pass only with:

```text
40 passed, 0 skipped, 0 failed
```

If skipped remains greater than 0:

- collect skip reasons with `-rs`
- verdict must be `PARTIAL_PASS_WITH_DB_EVIDENCE_GAP` or `BLOCKED_ENVIRONMENT`
- include exact root cause

## Report Requirements

Write report to:

```text
docs/ai-reports/lubuntu/2026-05-15_phase6_closeout_schema_contract_rerun.md
```

Report must include:

- GitHub Actions run URL
- runner name and id
- Leo invocation command
- branch and exact commit tested
- exact DB sanity commands and results
- exact pytest command
- exact pass/fail/xfailed/skipped counts
- skipped count
- skip reasons collected: Yes/No
- any live DB tests skipped: Yes/No
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
