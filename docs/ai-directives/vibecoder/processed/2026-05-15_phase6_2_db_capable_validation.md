Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: phase6-2-db-capable-validation
Priority: high
Created: 2026-05-15
Status: pending
Target-Branch: codex/phase6-2-receivables-mvp-2026-05-13
Validation-Scope: phase6-2-db-capable-targeted
Allow-Code-Changes: false
Allow-Product-Push: false

# Phase 6.2 DB-Capable Targeted Validation

Objective:
Validate Phase 6.2 receivables and credit-payment related backend behavior in Lubuntu DB-capable environment.

## Forbidden Actions

1. No product code modifications.
2. No test code modifications.
3. No product branch push.
4. No merge.
5. No `git reset --hard`.
6. No full pytest suite (`pytest` without file filters).
7. No Docker rebuild unless environment dependency is missing AND CTO is consulted first.
8. No delegation to Vibecoder chat agent for test execution.

## Required Setup Evidence

- `git fetch origin --prune`
- Checkout detached at `origin/codex/phase6-2-receivables-mvp-2026-05-13`
- Commit hash recorded
- `git status` clean (no uncommitted changes)
- Python version
- Poetry version
- PostgreSQL status (running / version)
- Redis status if relevant
- Environment variables used, with secrets redacted

## Required Validation Commands

1. **Backend app import / route smoke** (if supported by the project)
2. **Targeted receivables tests:**
   ```
   poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short
   ```
3. **Phase 5/6 payment regression:**
   ```
   REPORTING_USER_PASSWORD=<redacted> poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
   ```
4. **DB schema/migration sanity** (if environment supports it):
   ```
   poetry run pytest tests/test_payments_schema_contract.py -q --tb=short
   ```

### Execution Rules

- Do not silently skip any command.
- If a command cannot run due to environment limitations, mark `BLOCKED_ENVIRONMENT` and include the exact error message.
- Record exact pass/fail/xfail/skip counts for every test command.

## Required Report

**Path:** `docs/ai-reports/lubuntu/2026-05-15_phase6_2_db_capable_validation.md`

Report must include:
- GitHub Actions run URL
- Runner name/id
- Leo invocation command
- Branch and commit tested
- Exact commands executed (copy-paste, not paraphrased)
- Exact pass/fail/xfail/skip counts per command
- Skipped command explanation, if any
- `git status` before and after
- Verdict (exactly one):
  - `PASS_FOR_CTO_REVIEW`
  - `FAIL_FOR_CTO_REVIEW`
  - `BLOCKED_ENVIRONMENT`
  - `INSUFFICIENT_EVIDENCE`

## Pass Criteria

- No product code changed
- No product branch pushed
- Target branch/commit exact match
- All required commands either pass OR are explicitly blocked by environment with documented evidence
- No silent test narrowing (every required test file must appear in the command)

## Execution Path

GitHub Actions → runner ivy-20149 → `run_directive.sh` v2 → Leo headless executor
