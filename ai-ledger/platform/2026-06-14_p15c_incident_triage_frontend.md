# P15-C Incident Triage Frontend -- Ledger

**Date:** 2026-06-14
**Branch:** `codex/platform-p15bcd-incident-triage-batch-2026-06-14`
**Base:** `5bbd75c` (origin/platform-dev -- P15-A contract merge)
**HEAD:** Final pushed branch HEAD externally verified after push.
**Author:** Codex (Claude worker)

---

## Summary

P15-C adds the read-only Incident Triage view on top of the P15-B snapshot API.
It renders overall status, DB probe, tenant health sample counts, signals, and
always-visible unavailable/degraded reasons and graceful-degraded state. It
honors unknown != healthy (gray) and null != 0 (N/A). No mutation controls, no
tenant business fields, no credentials/DSN/host/port.

---

## Modified Files

- `frontend/src/types/platformIncident.ts` -- new: 5 contract TS interfaces + helpers
- `frontend/src/types/__tests__/platformIncident.test.ts` -- new: type/helper tests
- `frontend/src/services/platformApi.ts` -- added `getIncidentTriageSnapshot`
- `frontend/src/services/__tests__/platformOpsApi.test.ts` -- added P15 path test
- `frontend/src/pages/platform/ops/IncidentTriagePage.tsx` -- new read-only page
- `frontend/src/pages/platform/ops/__tests__/IncidentTriagePage.test.tsx` -- new
- `frontend/src/router/AppRouter.tsx` -- added `/platform/ops/incidents/triage` route (under existing PlatformRoute guard)
- `frontend/src/components/layout/Sidebar.tsx` -- added "Incident Triage" link (platform operator visible)
- `ai-ledger/platform/2026-06-14_p15c_incident_triage_frontend.md` -- this ledger

No lockfile change (`pnpm install --frozen-lockfile`). No new dependencies.

---

## Checks

- Frontend suite: **194 passed (22 files)**, 0 failed. Includes new IncidentTriage
  page tests (title/read-only, no mutation, no sensitive/business fields, loading,
  real snapshot render, graceful-degraded + reasons, null != 0 N/A), type tests,
  and the P15 service-path test.
- `git diff --check` -- clean.
- non-ASCII scan on new/changed frontend + ledger: 0 hits (ASCII-only).
- Forbidden path audit: only frontend platform-ops + types + services + ledger
  touched; no product pages, no backend, no migrations.

---

## Security / UX

- Read-only: no action buttons; route is GET-only via the P15-B API.
- unknown != healthy: unknown overall status is gray via PlatformStatusBadge.
- null != 0: nullable counts/latency render "N/A", never "0".
- unavailable_reason / degraded_reason always rendered when present.
- graceful-degraded badge + explanation shown when set.
- No tenant business fields (orders/payments/invoices/customers) rendered.
- No credentials/DSN/host/port/raw pool.status() string shown.

---

## Risk

LOW. New read-only page + types + service method; no shared state, no new deps,
no lockfile change. Reuses existing PlatformRoute guard + PlatformStatusBadge.

---

## Blockers

None.
