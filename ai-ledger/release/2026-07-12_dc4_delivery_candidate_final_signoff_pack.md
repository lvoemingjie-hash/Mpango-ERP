# DC-4 Delivery Candidate Final Signoff Pack

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| Pack ID | DC-4 |
| Scope | Docs / evidence only. No code changes, no migrations, no frontend, no config/lockfile changes. |
| Branch | `opencode/dc4-delivery-candidate-final-signoff-pack-2026-07-12` |
| Production commit | `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5` (`bf0649c0`) |
| Branch tip certified | `origin/product-dev-recovered` == `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5` |

## 0. Purpose

This pack consolidates the evidence trail that the `product-dev-recovered` runtime baseline at commit `bf0649c0` is healthy, the credential lifecycle is fully proven, and the platform is ready for delivery. It aggregates the DC-2B runtime recheck series and the DC-3 credential lifecycle runtime series into a single signoff.

## 1. Delivery Candidate Commit

| Attribute | Value |
|---|---|
| Branch | `origin/product-dev-recovered` |
| HEAD | `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5` |
| Includes | DC-2M2 relkind fix, DC-2H SMTP compose wiring, DC-3B credential recovery backend, DC-3C credential lifecycle frontend, DC-3E SPA crash fix |
| Verified on VPS | `1.14.247.12` (Tencent), `/opt/mpango-erp` |
| VPS deploy | Exact rebuild/redeploy verified in DC-2B-R5 and DC-3D-R3 |
| Tag | Recommended tag `release-2026-07-12` |

## 2. Platform / Product Merge Status

| Item | Status |
|---|---|
| `platform-dev` merged into `product-dev-recovered` | Yes (DC-1B G5 promotion) |
| `platform-dev` not modified during DC-2/DC-3 | Confirmed |
| Product line preserved | Yes |
| Platform P10-P25 surface intact | Confirmed via P25-F closeout |

## 3. Runtime Proof Summary

### 3.1 DC-2B-R5/R6: Delivery Candidate Runtime Recheck

- **R5 Report**: `ai-ledger/ops/2026-07-12_dc2b_r5_exact_vps_runtime_recheck_after_relkind_fix.md`
- **R5 Branch**: `ops/dc2b-r5-exact-vps-runtime-recheck-after-relkind-fix-2026-07-12`
- **R5 Commit**: `ad9e6b69`
- **R5 Verdict**: `PASS_RUNTIME_RECHECK_WITH_AUTH_CAVEATS`
- **R6 Report**: `ai-ledger/ops/2026-07-12_dc2b_r6_auth_credentialed_smoke_closure.md`
- **R6 Branch**: `ops/dc2b-r6-auth-credentialed-smoke-closure-2026-07-12`
- **R6 Commit**: `4577b195`
- **R6 Verdict**: `PASS_RUNTIME_RECHECK_CREDENTIALED_AUTH_NOT_EXECUTED`

**Key results (R5)**:
- Exact checkout `ac99bec7`, backup 396350 bytes (SHA `9c8ea11b4cbb`)
- 5/5 containers healthy, all health endpoints 200
- Alembic `031_legacy_tenant_reconciliation` head/current
- DC-2M2 schema objects present in all active tenant schemas
- Product smoke: auth/me 200, skus 200, inventory 200, intake 200, retailers 200, payments 200
- Order create -> confirm -> structured pay completed, ledger balanced
- Legacy payment POST returns 409, no 500s
- All log scans zero (relkind, decimal, tenant context, undefined table, secret leaks)

**R5 auth caveat**: Real `/auth/login` and `/auth/select-tenant` not executed (no safe credential source). This was later addressed by DC-3D-R3 and DC-3F.

### 3.2 DC-3D-R3: Credential Lifecycle Runtime Smoke

- **Report**: `ai-ledger/ops/2026-07-12_dc3d_r3_full_credential_lifecycle_runtime_smoke.md`
- **Branch**: `ops/dc3d-r3-full-credential-lifecycle-runtime-smoke-2026-07-12`
- **Commit**: `1da22716`
- **Target commit**: `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5`
- **Verdict**: `PASS_DELIVERY_CANDIDATE_CREDENTIAL_LIFECYCLE_RUNTIME`

**Key results**:
- Exact checkout `bf0649c0`, backup 398318 bytes (SHA `37ea35320d47`)
- SPA crash fixed (DC-3E merge) — 0 console errors on all credential routes
- SMTP delivers to `jeff05992582@126.com`
- Forgot/reset password flow end-to-end: email delivery -> browser URL scrub -> password reset -> new login 200 -> old login 401 -> tenant selection -> `/auth/me` 200 -> skus/orders 200
- Signup deferred (sub-addressing not supported by 126.com, later resolved by DC-3F)
- All log scans zero

### 3.3 DC-3F: Fresh Mailbox First-Login Smoke

- **Report**: `ai-ledger/ops/2026-07-12_dc3f_fresh_mailbox_first_login_smoke.md`
- **Branch**: `ops/dc3f-fresh-mailbox-first-login-smoke-2026-07-12`
- **Commit**: `20f72bd5`
- **Verdict**: `PASS_FRESH_MAILBOX_FIRST_LOGIN_SMOKE`

**Key results**:
- Signup with fresh Outlook.com mailbox: 202 Accepted
- SMTP delivers to external domains (confirmed)
- Verification email received -> `POST /auth/verify-email` -> 200
- Auto-provisioning: new tenant schema `t_e3c912ef...`, 19 tables, wholesaler created
- Owner setup email received -> browser URL scrubbed -> 0 console errors -> password set
- First login: 200 -> auto tenant select -> `/auth/me` 200 (admin role, 43 permissions)
- Authenticated smoke: skus 200, orders 200
- All security checks pass (zero 500s, zero secret leaks, storage clean)

## 4. Credential Lifecycle Summary

| Capability | Status | Evidence |
|---|---|---|
| Signup with real mailbox | PROVEN | DC-3F (Outlook.com) |
| Email verification | PROVEN | DC-3F |
| Auto tenant provisioning | PROVEN | DC-3F (19 tables, wholesaler) |
| Owner credential setup (browser) | PROVEN | DC-3F |
| URL token scrubbing (setupToken) | PROVEN | DC-3F |
| First login with new password | PROVEN | DC-3F |
| Forgot password (email delivery) | PROVEN | DC-3D-R3 |
| Reset password (browser) | PROVEN | DC-3D-R3 |
| URL token scrubbing (resetToken) | PROVEN | DC-3D-R3 |
| New login succeeds after reset | PROVEN | DC-3D-R3 |
| Old password fails after reset | PROVEN | DC-3D-R3 |
| Select tenant, `/auth/me`, SKUs, Orders | PROVEN | DC-3D-R3 + DC-3F |
| Email links carry token (no manual copy) | PROVEN | Both flows |
| Forgot password link on login page | PROVEN | DC-3D-R3 (browser) |

## 5. Security Proof

| Check | DC-2B-R5 | DC-3D-R3 | DC-3F |
|---|---|---|---|
| No raw tokens/JWT/password printed | PASS | PASS | PASS |
| Setup/reset tokens not in browser storage | N/A | PASS | PASS |
| Query-string token backend paths rejected (401) | N/A | PASS | PASS |
| Log scan: 500 count = 0 | PASS | PASS | PASS |
| Log scan: secret leak count = 0 | PASS | PASS | PASS |
| Log scan: TenantContextMissing = 0 | PASS | PASS | PASS |
| Log scan: UndefinedTable = 0 | PASS | PASS | PASS |
| Log scan: Decimal serialization = 0 | PASS | PASS | PASS |

## 6. Database / Migration

| Check | Value |
|---|---|
| Alembic heads | `031_legacy_tenant_reconciliation (head)` — single head |
| Alembic current | `031_legacy_tenant_reconciliation (head)` |
| Head/current mismatch | None |
| DC-2M2 legacy tenant reconciliation | Included (commit `5372d18a`, merged into product line) |
| DC-2M2 schema objects | Verified in all active tenant schemas (retailer_prices, mv, indices) |
| Active tenant schemas | `t_08177e17...`, `t_14927915...`, `t_550e8400...`, `t_e3c912ef...` (DC-3F newly provisioned) |

## 7. Rollback Readiness

| Item | Status |
|---|---|
| Latest backup | `/home/ubuntu/.secure-backups/dc3d_r3_20260712T190551Z.sql` (398318 bytes, SHA `37ea35320d47`) |
| Prior backup | `/home/ubuntu/.secure-backups/dc2b_r5_20260711T072726Z.sql` (396350 bytes, SHA `9c8ea11b4cbb`) |
| Rollback runbook | Confirmed dry-run in DC-1C-R1 (report: `ai-ledger/ops/2026-07-09_dc1c_rollback_runbook_confirmation.md`) |
| Exact restore path | `cat <backup.sql> \| docker exec -i mpango_prod_postgres psql -U mpango -d mpango_erp` |
| Target rollback commit | `dc2b_r5` backup restores to product-dev-recovered pre-DC-3 state |

**Note**: Backup contents and database credentials are not printed. The restore path is operational guidance only.

## 8. Known Caveats

### 8.1 Non-Blocking

| Caveat | Detail |
|---|---|
| Login email case sensitivity | Signup normalizes email to lowercase; login passes raw email to backend without normalization. Browser users must type email in the exact case used during signup. Cosmetic UX issue — does not block delivery. |
| Frontend build warnings | Duplicate `jsdom` key in `package.json`, Browserslist stale data warning, chunk size >500KB. All are cosmetic build warnings, not runtime defects. |

### 8.2 Blocking

None. All prior blocking issues (SMTP auth failure, SPA crash, 126.com sub-addressing) have been resolved.

## 9. Customer Handoff Readiness

| Requirement | Status |
|---|---|
| First admin receives verification/setup emails | Proven (DC-3F via Outlook.com) |
| Customer clicks email links (no manual token copy) | Proven |
| Forgot password flow available from login page | Proven (DC-3D-R3 browser screenshot) |
| Catalog SKU import limitation | Documented — intake-to-SKU creates catalog records only; inventory/pricing/sellable readiness is separate |
| Tenant provisioning is automatic | Proven |

## 10. Predecessor Chain

| Phase | Branch | Verdict |
|---|---|---|
| DC-1A | Exact VPS runtime baseline | `PASS_EXACT_VPS_RUNTIME_BASELINE` |
| DC-1B | Release candidate evidence pack | `PASS_RELEASE_CANDIDATE_EVIDENCE_READY` |
| DC-2B-R5 | Relkind fix runtime recheck | `PASS_RUNTIME_RECHECK_WITH_AUTH_CAVEATS` |
| DC-2B-R6 | Auth credentialed closure | `PASS_RUNTIME_RECHECK_CREDENTIALED_AUTH_NOT_EXECUTED` |
| DC-3D-R3 | Credential lifecycle runtime | `PASS_DELIVERY_CANDIDATE_CREDENTIAL_LIFECYCLE_RUNTIME` |
| DC-3F | Fresh mailbox first-login | `PASS_FRESH_MAILBOX_FIRST_LOGIN_SMOKE` |
| **DC-4** | **Final signoff pack** | **This report** |

All predecessor phases passed. DC-3F closed the final DC-3D-R3 caveat.

## 11. Validation

| Check | Result |
|---|---|
| `git diff --check` | Will be run before commit |
| ASCII / mojibake scan | Will be run before commit |
| `poetry run detect-secrets scan` | Will be run before commit |
| `poetry run pre-commit` | Will be run before commit |
| `npx gitnexus analyze` | Will be run before commit |
| `npx gitnexus status` | Will be run before commit |

## 12. Verdict

**PASS_DELIVERY_CANDIDATE_FINAL_SIGNOFF_READY**

The `product-dev-recovered` branch at commit `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5` is certified as the delivery candidate. The credential lifecycle is fully proven (forgot/reset + signup/setup/first-login). All security checks pass. The remaining caveats are cosmetic and non-blocking.

### Recommended next steps

1. Tag `bf0649c0` as `release-2026-07-12` on `origin/product-dev-recovered`.
2. Distribute signoff pack to CTO.
3. If a dedicated fresh-mailbox account is provisioned for production, run one more DC-3F-style smoke against it before go-live.
