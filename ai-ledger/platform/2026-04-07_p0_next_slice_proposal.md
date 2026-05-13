# Platform Track P0 — Next Slice Proposal (Corrected)

**Date**: 2026-04-07
**Agent**: Platform AI (Vibecoder)
**Branch**: platform-dev
**Track**: Platform P0 - Next slice proposal
**Status**: Corrected — awaiting CTO approval

---

## Chosen Next Slice

**Platform Audit Log Boundary** — `public.platform_audit_logs`

An append-only, public-schema table for platform-level administrative actions, with a read-only query API and internal appender service.

## CTO-Approved Contract (Corrected)

| Aspect | Rule |
|--------|------|
| External API | Read-only only (GET list + GET detail) |
| Write surface | Internal appender service only — NO external write endpoint |
| wholesaler_id | Nullable FK to public.wholesalers.id (NULL for global actions) |
| Auth | No changes |
| Billing | No changes |
| Tenant schema | No changes |

## Corrections Applied (P1)

1. **Removed write endpoint ambiguity** — proposal previously mentioned "one write endpoint" in scope summary; corrected to "internal appender service, no external write endpoint"
2. **Added FK to wholesaler_id** — previously proposed "no FK to keep it simple"; corrected to nullable FK preserving referential integrity

## Proposal Location

`docs/arch/platform-next-slice-proposal.md`

## Status

IMPLEMENTATION-BLOCKED — awaiting CTO approval of corrected proposal.
