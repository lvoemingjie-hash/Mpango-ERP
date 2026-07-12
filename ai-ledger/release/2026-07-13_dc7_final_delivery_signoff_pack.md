# DC-7 Final Delivery Signoff Pack

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| Pack ID | DC-7 (Final Delivery Signoff Pack Refresh) |
| Scope | Docs / evidence only. No code changes, no migrations, no frontend, no config/lockfile changes. |
| Branch | `opencode/dc4-delivery-candidate-final-signoff-pack-2026-07-12` (updated; DC-4 file left unchanged) |
| Delivery baseline commit | `547b0b294aa387d6179f53eca3ec162532a1e29e` (`547b0b29`) |
| Branch tip certified | `origin/product-dev-recovered` == `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| Supersedes | DC-4 (`bf0649c0` baseline); DC-7 certifies the newer `547b0b29` baseline |

## 0. Purpose

This pack refreshes the final delivery signoff after DC-5A/DC-5B/DC-6B/DC-6C.
It supersedes DC-4 and certifies the new delivery baseline at
`547b0b294aa387d6179f53eca3ec162532a1e29e`. All known red-team delivery
blockers are fixed and runtime-closed.

## 1. Delivery Candidate Commit

| Attribute | Value |
|---|---|
| Branch | `origin/product-dev-recovered` |
| HEAD | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| Commit subject | `fix(dc6b): fail closed malformed export job ids` |
| Includes | DC-2M2 relkind fix, DC-2H SMTP compose wiring, DC-3B credential recovery backend (+ R1/R2/R3), DC-3C credential lifecycle frontend, DC-3E SPA crash fix, DC-5A export permission hardening + login email normalization + RBAC contract cleanup, DC-6B malformed export job_id fail-closed fix |
| Verified on VPS | `1.14.247.12` (Tencent), `/opt/mpango-erp` (DC-5B, DC-6C) |
| Tag | Recommended tag `release-2026-07-13` |

### 1.1 Changes since DC-4 baseline (`bf0649c0`)

| Commit | Description |
|---|---|
| `bde03da4` | DC-5A: harden exports and normalize login email |
| `547b0b29` | DC-6B: fail closed malformed export job ids |

DC-5A delivers:
- Export permission hardening (exports endpoints gated by `exports:create`).
- Login email normalization (mixed-case emails normalized to lowercase at
  login, matching the signup normalization).
- RBAC contract cleanup (route policy allowlist and minimality tests aligned
  with the new public auth endpoints).

DC-6B delivers:
- Malformed export job IDs (e.g. `not-a-uuid`) now return controlled 400
  `INVALID_EXPORT_ID` instead of 500 with a UUID parser exception leak.

## 2. Runtime Evidence

### 2.1 DC-5B: Pre-Delivery Runtime Smoke

| Field | Value |
|---|---|
| Report | `ai-ledger/ops/2026-07-12_dc5b_pre_delivery_runtime_smoke.md` |
| Commit | `93eee7df` |
| Verdict | `PASS_PRE_DELIVERY_RUNTIME_SMOKE` |

**Key evidence:**
- Mixed-case login: PASS (email normalized, login succeeds).
- Export permission runtime: PASS (authenticated export create returns
  controlled 422 on wrong body; unauthenticated returns 401).
- SPA no crash: PASS (all credential routes 200, `#root` present, no crash
  string in logs).
- Log scans zero: 500=0, TenantContextMissing=0, UndefinedTable=0, Decimal
  serialization=0, secret leak=0.

### 2.2 DC-6C: Export Malformed ID Runtime Recheck

| Field | Value |
|---|---|
| Report | `ai-ledger/ops/2026-07-13_dc6c_export_malformed_id_runtime_recheck.md` |
| Commit | `2141a321` |
| Verdict | `PASS_EXPORT_MALFORMED_ID_RUNTIME_RECHECK` |

**Key evidence:**
- `GET /exports/not-a-uuid` (auth) -> 400 `INVALID_EXPORT_ID` (no leak).
- `GET /exports/not-a-uuid/download` (auth) -> 400 `INVALID_EXPORT_ID` (no leak).
- `GET /exports/00000000-0000-0000-0000-000000000000` (auth) -> 404
  `EXPORT_NOT_FOUND`.
- `GET /exports/00000000-0000-0000-0000-000000000000/download` (auth) -> 404
  `EXPORT_NOT_FOUND`.
- All above without auth -> 401 (auth gate before handler).
- Response bodies do NOT contain: "badly formed hexadecimal UUID string",
  "ValueError", "traceback", "stack trace".
- Log scans zero: 500=0, EXPORT_STATUS_FAILED=0, EXPORT_DOWNLOAD_FAILED=0,
  secret=0, TenantContextMissing=0, UndefinedTable=0, Decimal=0,
  badly-formed-uuid=0, ValueError/traceback=0.

### 2.3 Prior runtime evidence (carried forward from DC-4)

| Evidence | Status |
|---|---|
| DC-2B-R5 exact VPS runtime recheck | PASS (containers healthy, Alembic 031, product smoke, order/pay ledger) |
| DC-2B-R6 auth credentialed smoke | PASS (login/select-tenant/me/SKUs/Orders all 200) |
| DC-3B credential recovery (15 tests) | PASS (forgot/reset, multi-tenant fan-out, tmap truth gate) |
| DC-3D-R1 SMTP credential gate | PASS (SMTP auth 235, forgot-password token issued, SMTP delivered) |
| DC-3D-R3 full lifecycle (if run) | See DC-3D-R3 report |
| Alembic head/current | `031_legacy_tenant_reconciliation` (single head) |

## 3. Third-Party Red-Team Audit Summary

### 3.1 DC-6A: Pre-Delivery Red-Team Defect Hunt

| Field | Value |
|---|---|
| Report | `docs/ai-reports/red-team/2026-07-12_dc6a_pre_delivery_red_team_defect_hunt.md` |
| Commit | `bc9fb11a` |
| Verdict | `PASS_WITH_NON_BLOCKING_FINDINGS` |

**Initial red-team findings:**
- The red-team hunt tested 7 attack areas (credential lifecycle, tenant
  isolation, RBAC/export, orders/payments, data intake, frontend runtime,
  security/leak).
- One P0 was found: malformed export job IDs (`/exports/not-a-uuid`) caused a
  500 with UUID parser exception text leakage.

**P0 closure:**
- Fixed by DC-6B (`547b0b29`): malformed IDs now return 400
  `INVALID_EXPORT_ID` with no exception text.
- Runtime-closed by DC-6C (`2141a321`): proven on the live VPS that malformed
  IDs return 400, well-formed fake UUIDs return 404, unauthenticated requests
  return 401, and all log scans are zero.

**P0/P1 delivery blockers status:** All P0 and P1 delivery blockers are now
**closed**. The remaining P2 findings are coverage gaps (mailbox-dependent and
browser-automation-dependent tests), not product defects.

## 4. Caveats

### 4.1 Accepted post-MVP hardening items (non-blocking)

| Item | Severity | Status |
|---|---|---|
| Raw JWT in browser storage (localStorage) | P2 | Accepted post-MVP hardening item; not hidden. The frontend stores access/refresh tokens in localStorage. Post-MVP hardening should evaluate httpOnly cookies or session-based alternatives. |
| Frontend deprecation/warnings (React act, bundle size) | P2 | Non-blocking; cosmetic warnings only. |
| Browser stale-auth-state injection not adversarially tested | P2 | Requires browser automation; DC-3E header crash fix is deployed. |

### 4.2 Caveats removed (fixed since DC-4)

| Item | Fixed by | Runtime-proven by |
|---|---|---|
| Login email case sensitivity | DC-5A (`bde03da4`) | DC-5B (mixed-case login PASS) |
| RBAC doc drift | DC-5A (`bde03da4`) | DC-5B (route policy tests pass) |
| Malformed export job_id 500 + leak | DC-6B (`547b0b29`) | DC-6C (400 INVALID_EXPORT_ID, no leak) |

## 5. Security Proof

| Control | Status | Evidence |
|---|---|---|
| No raw token/JWT/password/SMTP/DB secrets printed | PASS | DC-5B, DC-6C: all response bodies and logs scanned; zero secret values found |
| Query-string token rejection (setup/reset) | PASS | DC-6A: setup-credential and reset-password query-string tokens rejected (401) |
| Malformed export IDs no longer leak UUID parse exception | PASS | DC-6C: 400 INVALID_EXPORT_ID, no "badly formed hexadecimal" / "ValueError" / "traceback" in body |
| Log scans zero across latest runtime proofs | PASS | DC-5B: 500=0, secret=0, TenantContextMissing=0, UndefinedTable=0, Decimal=0. DC-6C: all scan patterns = 0 |
| Export permission hardening | PASS | DC-5A: exports gated by `exports:create`; DC-5B: unauth 401, auth 422 on wrong body |
| Login email normalization | PASS | DC-5A: mixed-case normalized; DC-5B: mixed-case login PASS |
| Credential lifecycle (forgot/reset/setup) | PASS | DC-3B 15 tests green; DC-3D-R1 SMTP delivery proven; DC-6A red-team credential attacks all controlled |
| Multi-tenant password consistency (tmap) | PASS | DC-3B-R1/R2: verified-only matches, signed tmap, select-tenant per-tenant user_id |
| Alembic single head | PASS | `031_legacy_tenant_reconciliation` (single head, no branches) |

## 6. Rollback

| Item | Value |
|---|---|
| Latest backup (DC-6C) | `/home/ubuntu/.secure-backups/dc6c_20260712T223753Z.sql` |
| Backup size | 461,831 bytes |
| Backup SHA256 prefix | `3b263368ac08` |
| Rollback procedure | Application-version rollback + DB restore from verified backup (DC-1C runbook pattern) |
| Backup contents printed | No (never) |

## 7. Final Verdict

**PASS_FINAL_DELIVERY_SIGNOFF_READY**

All known red-team delivery blockers are fixed and runtime-closed at
product-dev-recovered commit 547b0b29.
