# Platform Governance Doc Reconciliation

Date: 2026-05-07
Branch: platform-dev
Status: complete - ready for CTO review

## Context

The Lubuntu-side platform sync pushed commit `3b88fa5` to `origin/platform-dev`.
That commit left `docs/ai/PROJECT.md` as a platform-authored parallel project
overview instead of the shared canonical product-line project log.

CTO directed platform governance docs to reconcile back to the single shared
memory model before Goose resumes platform work.

## Changes

- Replaced `docs/ai/PROJECT.md` with the canonical version from
  `origin/product-dev-recovered`.
- Replaced `docs/ai/README.md` with the canonical version from
  `origin/product-dev-recovered`.
- Kept `docs/PROJECT_HANDOFF.md` as platform supplemental context only.
- Updated `.claude/skills/generated/mpango-platform-handoff/SKILL.md` so
  `docs/ai/PROJECT.md` is described as the canonical project log.
- Restored `.gitignore` to the shared baseline and kept only the safe agent
  runtime/editor ignore additions from the Lubuntu sync.
- Removed ignores for `ai-ledger/cto/` and `ai-ledger/test/`; ledger history
  should remain visible unless a separate archival policy is approved.

## Validation

- Scope is governance-doc alignment only.
- No product business code changed.
- No platform feature code changed.
- No branch promotion or product branch mutation performed.

## Follow-Up

Goose should fetch/pull `origin/platform-dev` after this reconciliation is
visible remotely, then run platform-line takeover alignment before any new
platform proposal or implementation work.
