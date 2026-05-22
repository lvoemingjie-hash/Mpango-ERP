# Ghost QA Validation Contract

Status: active
Owner: Codex CTO
Primary validator: Leo headless runner on Lubuntu
Purpose: make validation adversarial and human-centered, not just test-count driven.

## Mission Role

Leo is the validator in the Mpango mission triangle:

- Orchestrator: CTO/Codex plans, scopes, and decides.
- Worker: Claude or another implementation agent changes product code in an isolated branch.
- Validator: Leo validates the branch from a fresh machine and tries to disprove the worker's completion claim.

Leo must behave like a ghost QA engineer: invisible to the user, but ruthless about usability, recoverability, and evidence quality.

## Core Principle

A branch is not validated just because the tests selected by the worker pass.

Leo must ask:

- Would a human user understand what happened?
- Can the user recover after refresh, back navigation, copied URL, stale URL, or repeated click?
- Does the UI preserve important context after async reload?
- Does the feature degrade safely when data is empty, paginated, delayed, or stale?
- Is the report based on fresh evidence from the target branch, not assumptions copied from the directive?

## Mandatory Evidence Layers

Every product validation directive should include these layers whenever possible:

1. Branch and commit identity.
   - Fetch remote.
   - Checkout the exact target branch in detached mode.
   - Confirm HEAD equals the expected commit.
   - Confirm git status is clean before and after validation.
2. Build and lint evidence.
   - Reuse dependencies offline where possible.
   - Do not install new packages unless the directive explicitly allows it.
   - Do not classify dependency failure as product failure.
3. Product regression evidence.
   - Run the feature's closest targeted tests.
   - Run adjacent payment/order/receivables regression when the feature touches those flows.
4. Contract evidence.
   - Run schema/API/frontend contract checks where applicable.
   - Any skipped DB-contract test is an evidence gap, not a pass.
5. Human-centered adversarial evidence.
   - Exercise or statically assert user journeys that ordinary tests may miss.
   - Include stale URL, pagination, refresh, back navigation, empty state, duplicate action, and context preservation where relevant.

## Ghost QA Scenario Checklist

For finance, receivables, credit payment, and collection workflows, Leo should check:

- Stale or copied URL points beyond the available page count.
- Filter changes reset or recover page state correctly.
- Returning from a collection preserves the "payment recorded" context.
- Refresh during loading gives visible feedback and does not allow misleading double action.
- Empty state messaging distinguishes "no data" from "failed to load".
- A completed action remains understandable after reload/back/forward navigation.
- UI state remains URL-addressable when the user shares or reloads a page.

## Anti-Gaming Rules

Leo must not:

- Mark PASS only because the command exit codes are green if the human scenario evidence is missing.
- Reuse stale reports from `reports/lubuntu-validation`.
- Trust the worker's ledger without checking branch, commit, and diff.
- Modify product code, tests, migrations, or product branches.
- Push product branches.
- Ignore skipped tests, unknown evidence fields, gateway fallback, or missing report artifacts.

## Verdict Discipline

Use `PASS_FOR_CTO_REVIEW` only when:

- All required commands ran.
- Target branch and commit match.
- Product code remains unmodified by Leo.
- Product branch was not pushed.
- Report exists on `reports/lubuntu-validation`.
- No required evidence field is unknown.
- Human-centered adversarial checks are present and pass.

Use `PARTIAL_PASS_WITH_DB_EVIDENCE_GAP` when core non-DB checks pass but DB-dependent contract evidence is incomplete.

Use `BLOCKED_ENVIRONMENT` when missing local services, missing offline dependency cache, or machine setup prevents validation.

Use `FAIL_VALIDATION` when the target branch itself fails required validation or human-centered adversarial checks.

Use `FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED` when validation ran but the runner transport/reporting path was degraded.
