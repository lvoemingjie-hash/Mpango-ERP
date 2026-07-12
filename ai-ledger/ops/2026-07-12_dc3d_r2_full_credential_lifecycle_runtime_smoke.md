# DC-3D-R2 Full Credential Lifecycle Runtime Smoke

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| Task ID | DC-3D-R2 (Full Credential Lifecycle Runtime Smoke) |
| VPS | Tencent VPS `1.14.247.12` |
| Ops Branch | `ops/dc3d-r2-full-credential-lifecycle-runtime-smoke-2026-07-12` |
| Verdict | `STOP_AND_REPORT_CTO` |

## Summary

DC-3D-R2 cannot proceed. The explicit precondition is not met: **DC-3E
(`bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5`, "fix(dc3e): prevent header crash
on missing roles") is NOT merged into `origin/product-dev-recovered`**.

The task states:
> Precondition: DC-3E must be merged into product-dev-recovered before deploy.
> Target commit must include bf0649c0 or its merge descendant.

`origin/product-dev-recovered` tip is `51cfd227094235028f6a09fd173576e1ddb8caf5`.
`bf0649c0` exists only on `opencode/dc3e-frontend-spa-runtime-crash-fix-2026-07-12`
and is NOT an ancestor of `51cfd227`. The merge-base check confirms:
`git merge-base --is-ancestor bf0649c0 origin/product-dev-recovered` = false.

No deploy, no backup, no smoke was performed. No code was changed. No protected
branch was pushed.

## Precondition Evidence

| Check | Result |
|---|---|
| Required DC-3E commit | `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5` |
| `bf0649c0` resolves | Yes -- `fix(dc3e): prevent header crash on missing roles` |
| `bf0649c0` on `product-dev-recovered`? | **NO** |
| `bf0649c0` branch | `opencode/dc3e-frontend-spa-runtime-crash-fix-2026-07-12` only |
| `origin/product-dev-recovered` tip | `51cfd227094235028f6a09fd173576e1ddb8caf5` (`feat(dc3c): add credential lifecycle frontend`) |
| `51cfd227` == `bf0649c0`? | **NO** (DC-3E fix is a separate commit on top of `51cfd227`) |

## DC-3E Fix Scope (for CTO context)

The DC-3E fix is a small, focused change:
- `frontend/src/components/layout/Header.tsx` -- 5 lines (prevent crash on
  missing/undefined `roles`)
- `frontend/src/tests/Header.test.tsx` -- 46 lines (new test)
- `ai-ledger/product-ai/2026-07-12_dc3e_frontend_spa_runtime_crash_fix.md` -- 82 lines (ledger)
- Total: 3 files, +131/-2

It sits directly on top of `51cfd227` (1 commit ahead). Merging it into
`product-dev-recovered` is the CTO's decision; this agent does not push protected
branches.

## Current Deployed State (for reference)

| Check | Result |
|---|---|
| VPS `HEAD` | `51cfd227` (= `origin/product-dev-recovered` tip) |
| Frontend `/` | 200 (SPA HTML with `#root`) |
| Frontend `/login` | 200 |
| SMTP auth | SUCCEEDS (code 235, verified in DC-3D-R1) |
| `/health/live` | 200 |

The SPA currently renders at `51cfd227`, but the DC-3E header-crash fix
(preventing a crash when `roles` is missing/undefined) is not yet deployed.
Running the full browser credential lifecycle smoke without the DC-3E fix
risks hitting that crash during the proof, which would invalidate the result.

## What Was NOT Done

- No deploy (precondition not met).
- No DB backup (no deploy).
- No rebuild/redeploy (no deploy).
- No browser proof (no deploy).
- No forgot/reset smoke (precondition not met).
- No `product-dev-recovered` or `platform-dev` push.

## Guardrails

| Guardrail | Result |
|---|---|
| Do not push product-dev-recovered | PASS (not pushed) |
| Do not push platform-dev | PASS (not pushed) |
| No secrets printed | PASS (none accessed) |
| No deploy without precondition | PASS (stopped) |

## Verdict

**STOP_AND_REPORT_CTO**

Reason: the DC-3E precondition is not met. `bf0649c0` ("fix(dc3e): prevent
header crash on missing roles") must be merged into `origin/product-dev-recovered`
before DC-3D-R2 can proceed. Once the CTO merges DC-3E, DC-3D-R2 can run the
full credential lifecycle runtime smoke (exact checkout, deploy, browser proof,
forgot/reset proof, security checks) against the updated baseline.
