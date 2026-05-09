# Platform Track — Permanent Operating Rules

**Date**: 2026-04-09
**Agent**: Platform AI (Vibecoder)
**Branch**: platform-dev
**Status**: PERMANENT — applies to all future platform commits

---

## Rule 1: Self-Check Gates Before Every Commit

All 8 gates must PASS. Any FAIL → fix → rerun → commit only when all PASS.

| Gate | Checks |
|------|--------|
| Scope | Only task-scoped files; no auth/tenancy/business-table changes |
| Architecture | Schema-per-tenant preserved; platform references wholesalers.id; public schema only |
| API contract | No tuple-style responses; HTTPException/JSONResponse; read-only when required |
| Migration | FK in both ORM and migration; indexes match model; sane downgrade |
| Tests | Run tests; all pass; request-level tests when API surface changes |
| Boot/import | Backend imports; no circular/missing imports; router registration valid |
| Diff hygiene | No debug prints; no temp scripts; canonical ledger path ai-ledger/platform/ |
| CTO-question | Honest self-assessment: would CTO flag this? |

## Rule 2: Request-Level Tests Required for API Changes

When any API endpoint is added or modified, request-level tests MUST be included:
- List endpoint behavior (empty, pagination, filters)
- Detail endpoint (success, 404)
- Read-only contract (POST/PUT/PATCH/DELETE return 405)
- Use `app.dependency_overrides` to mock DB — no real infrastructure dependency

## Rule 3: Migration/Model DB-Contract Consistency

Every ORM relationship intended at runtime MUST be enforced at DB level:
- If model declares FK → migration must create FK
- If model declares unique index → migration must create unique index
- If model has server_default → migration must have matching server_default

## Rule 4: Diff Hygiene Mandatory

Before every commit:
- Remove all debug prints (grep for `print(` in changed files)
- Remove all temp scripts and local config drift
- Verify ledger uses canonical path `ai-ledger/platform/`
- Review own diff file by file

## Rule 5: Tool-First Execution

Never rely on unstated assumptions. Always:
- Read files directly before modifying
- Search repo directly for patterns and conventions
- Run tests directly and see actual results
- Inspect diffs directly before committing
- Use concrete evidence, not mental models

## Rule 6: No Push Until CTO Approval

Commit → present ledger + hash → await CTO review → push only after approval.

*Exception*: CTO explicitly instructs to push immediately.

---

## Effective Date

2026-04-09 — applies to all platform-track work going forward.
