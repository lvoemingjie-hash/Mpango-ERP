# AI Team Operating Rules Update

Date: 2026-05-08
Branch: product-dev-recovered
Status: complete - ready for CTO review

## Context

During Phase 6 credit-payment work, CodeBuddy required several CTO corrections
before the implementation matched the intended business rule. The root issue was
not effort, but incomplete self-checking against CTO constraints and missing
counterexample tests before reporting completion.

## Change

Added `docs/ai/AI_TEAM_OPERATING_RULES.md` and updated:

- `docs/ai/README.md`
- `docs/ai/PROJECT.md`

## New Rule

AI agents may not report `COMPLETE` only because code changed and tests passed.
Before CTO review, the relevant ledger must include:

- every CTO constraint
- implementation evidence for each constraint
- test evidence for each constraint
- counterexamples that could satisfy literal wording but violate CTO intent
- completion claim: `COMPLETE`, `PARTIAL`, or `BLOCKED`

## Validation

- Documentation-only change.
- No product code changed.
- No platform code changed.
- Rule is now in the canonical AI read order through `docs/ai/README.md`.
