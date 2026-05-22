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

## Ghost QA Maturity Tiers

Ghost QA is intentionally staged so validation becomes more human-real without making every sprint depend on a brittle full E2E stack on day one.

### Tier 0 - Structural Adversarial Contract

Tier 0 proves that the branch contains the safety behavior the sprint claims to add.

Examples:

- Source-level assertions for stale URL recovery.
- Source-level assertions that collection notice context is preserved.
- Source-level assertions that refresh/loading feedback exists.

Tier 0 is useful, but it is not enough for long-term MVP confidence because it can still reflect the worker's implementation shape.

### Tier 1 - Browser Capability Probe

Tier 1 proves the validation machine can support browser-level QA without changing product code.

Leo should check:

- Whether Playwright or a compatible browser automation package is available offline.
- Whether a system Chromium/Chrome executable is available.
- Whether frontend dependencies can be reused offline.
- Whether lint/build still pass before any browser probe is trusted.

If browser tooling is missing, classify as `BLOCKED_ENVIRONMENT`, not `PASS_FOR_CTO_REVIEW` and not product failure.

### Tier 1B - Browser Launch Probe

Tier 1B proves that browser capability is not only installed, but can actually launch headlessly and execute JavaScript.

Leo should check:

- Launch Playwright Chromium when Playwright is available.
- Otherwise launch system Chromium/Chrome in headless mode.
- Render a minimal local HTML probe.
- Execute a DOM assertion inside the browser.

If a package or binary is present but cannot launch, classify as `BLOCKED_ENVIRONMENT` unless the failure is clearly caused by product code.

### Tier 2 - Human Journey Browser Test

Tier 2 is the target Ghost QA level for product promotions.

Leo should drive a real browser or browser-compatible harness through user journeys such as:

- Open Finance with a stale high page URL.
- Confirm the UI recovers to the last valid page instead of showing a misleading empty state.
- Confirm collection confirmation survives recovery.
- Refresh while loading and confirm the user sees meaningful feedback.
- Use back/forward or reload and confirm URL-state remains coherent.

Use Tier 2 as the default for future high-risk finance, payment, order, and receivables work once Tier 1 capability is proven.

Tier 2 evidence must come from a real built frontend page, not only a source scan or standalone data URL. API mocking is allowed only through browser/network interception in the validation harness. The report must include an App Import/Ghost QA evidence line containing `ghost_qa_tier2_journey=pass(...)`; otherwise the Final Gate must fail the run.

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
- Mark PASS when report evidence contains `fail`, `blocked`, or `error` inside an App Import/Ghost QA evidence line.
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
