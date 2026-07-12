# DC-9 Final Release Tag + Customer Delivery Package

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| Task ID | DC-9 (Final Release Tag + Customer Delivery Package) |
| Mode | Docs / tag only. No code changes. |
| Delivery baseline | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| Release tag | `release-2026-07-13` |
| Tag object SHA | `7ff1ab3a665592c4f9b8088c0b0c141eba2911ff` (annotated) |
| Branch | `ops/dc9-final-release-tag-customer-delivery-package-2026-07-13` |
| Verdict | `PASS_FINAL_RELEASE_TAGGED_AND_CUSTOMER_DELIVERY_PACKAGE_READY` |

## 1. Baseline Verification

| Check | Result |
|---|---|
| `origin/product-dev-recovered` tip | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| Required commit | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| Match | YES (exact) |
| Worktree HEAD | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| Worktree status | clean (0 tracked changes) |
| `git log --oneline -1` | `547b0b29 fix(dc6b): fail closed malformed export job ids` |

## 2. Tag Creation

| Check | Result |
|---|---|
| Existing tag conflict check | `git ls-remote --tags origin release-2026-07-13` returned empty (no conflict) |
| Tag created | `git tag -a release-2026-07-13 547b0b29 -m "Mpango ERP delivery release 2026-07-13"` |
| Tag pushed | `git push origin refs/tags/release-2026-07-13` -> success |
| Remote tag proof | `7ff1ab3a665592c4f9b8088c0b0c141eba2911ff refs/tags/release-2026-07-13` |

## 3. Evidence Chain

| Evidence | Source | Verdict |
|---|---|---|
| DC-7 final signoff pack | `ai-ledger/release/2026-07-13_dc7_final_delivery_signoff_pack.md` (commit `9f4e8290`) | PASS_FINAL_DELIVERY_SIGNOFF_READY |
| DC-8 independent verification | `origin/reports/lubuntu-validation @ 2a860d0` | PASS_FINAL_INDEPENDENT_DELIVERY_SIGNOFF |
| DC-5B pre-delivery runtime smoke | `ai-ledger/ops/2026-07-12_dc5b_pre_delivery_runtime_smoke.md` (commit `93eee7df`) | PASS_PRE_DELIVERY_RUNTIME_SMOKE |
| DC-6C export malformed ID recheck | `ai-ledger/ops/2026-07-13_dc6c_export_malformed_id_runtime_recheck.md` (commit `2141a321`) | PASS_EXPORT_MALFORMED_ID_RUNTIME_RECHECK |
| DC-6A red-team defect hunt | `docs/ai-reports/red-team/2026-07-12_dc6a_pre_delivery_red_team_defect_hunt.md` (commit `bc9fb11a`) | PASS_WITH_NON_BLOCKING_FINDINGS |
| DC-3B credential recovery backend | 15 tests + R1/R2/R3 fixes | PASS_FOR_CTO_DC3B_REVIEW |
| DC-2B-R5/R6 runtime recheck | VPS exact checkout, containers, smoke | PASS |
| Alembic head/current | `031_legacy_tenant_reconciliation` (single head) | PASS |

## 4. What This Release Includes

- Tenant onboarding with email verification (signup -> verify-email -> auto-provision).
- Owner credential setup (setup-token -> set password -> first admin RBAC).
- Forgot/reset password (self-service recovery, hash-only tokens, multi-tenant fan-out).
- Login / select-tenant (identity JWT with signed tmap for verified tenants).
- SKU catalog / data intake MVP (catalog-only, no inventory/pricing/sellable).
- Orders / payments MVP (order create -> confirm -> structured pay, ledger balanced).
- Export hardening (permission-gated, malformed ID fail-closed, no exception leak).
- Platform/product merged baseline (P10-P25 platform surface + U6 onboarding).

## 5. Known MVP Limitations

- Catalog import does not create inventory, pricing, barcode, images, or
  sellable readiness (documented in `docs/MVP_LIMITATIONS.md`).
- Raw JWT browser storage (localStorage) accepted as post-MVP hardening item.
- Non-admin role mapping remains limited to MVP-tested paths.
- Frontend build warnings (React act, bundle size) are non-blocking.

## 6. Rollback Reference

| Item | Value |
|---|---|
| Latest backup (DC-6C) | `/home/ubuntu/.secure-backups/dc6c_20260712T223753Z.sql` |
| Backup size | 461,831 bytes |
| Backup SHA256 prefix | `3b263368ac08` |
| Rollback procedure | Application-version rollback + DB restore (DC-1C runbook pattern) |

## 7. Security Confirmation

- No raw token/JWT/password/SMTP/DB URL/private key printed in this report.
- No real email addresses printed.
- Query-string token rejection remains enforced.
- Malformed export IDs return 400 INVALID_EXPORT_ID (no exception leak).
- Log scans zero across all runtime proofs.

## 8. Push Confirmation

- Release tag `release-2026-07-13` pushed to origin.
- Docs branch `ops/dc9-final-release-tag-customer-delivery-package-2026-07-13` pushed.
- `product-dev-recovered` NOT pushed.
- `platform-dev` NOT pushed.

## 9. Verdict

**PASS_FINAL_RELEASE_TAGGED_AND_CUSTOMER_DELIVERY_PACKAGE_READY**

The delivery candidate at `547b0b29` is tagged `release-2026-07-13`, the
customer delivery package is prepared, and all evidence chains confirm the
release is ready.
