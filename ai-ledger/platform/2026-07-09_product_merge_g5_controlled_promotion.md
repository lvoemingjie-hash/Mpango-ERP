# G5 Controlled Platform-to-Product Promotion

Verdict: PASS_FOR_CTO_PRODUCT_PROMOTION

Date: 2026-07-09

## 1. Branches and SHAs

- Worktree: C:\Users\Jeff0\MPANGO ERP\_g5_controlled_promotion_2026-07-09
- Branch: codex/product-merge-g5-controlled-promotion-2026-07-09
- Product base: origin/product-dev-recovered @ 0879314c20aad0fbaf235d6561343e228fd11693
- Platform source: origin/platform-dev @ 12c5ee557876498240b1a36cc850d030d7bd8293
- Merge base: 8332f81e78a7103a7271d7199067f82c461a8ada
- G4 evidence base: 2ebdc6939b1645b670175159922411eae1c36b29
- G5 repair commit: efddc3245e9531844cbc54ebd32807f4fd2b2707

Protected branches were not pushed during G5.

## 2. Execution Summary

G5 started from a fresh product worktree based on origin/product-dev-recovered. A direct merge of origin/platform-dev reproduced the same conflict family documented by G1/G2:

- backend/api/v1/platform/audit.py
- backend/api/v1/platform/stats.py
- backend/api/v1/platform/tenants.py
- backend/tests/test_platform_audit_api.py
- backend/tests/test_platform_stats_api.py
- docs/ai/README.md
- frontend/pnpm-lock.yaml
- frontend/src/components/layout/Sidebar.tsx
- frontend/src/router/AppRouter.tsx

Because local branch codex/product-merge-g4-promotion-candidate-2026-07-09 was already the reviewed and validated resolution of the same product base and same platform source, G5 aligned the candidate tree to the G4-R1 evidence tip, then repaired the missing G2-R2 regression-fix commit on top.

## 3. Resolution Policy

- Alembic: product chain 020-028 preserved; platform 020/021 represented as 029/030; single head is 030_platform_backup_status_source.
- Auth/RBAC: product U6 auth/RBAC and platform identity-only PlatformRoute behavior preserved.
- Platform API: platform endpoints keep get_platform_db, require_platform_operator, and redaction behavior.
- Product business UI: no product business UI conflict was resolved in G5; G4 evidence remains the source of product smoke proof.
- Package/lockfiles: G4 candidate contains regenerated pnpm-lock.yaml. G5 made no frontend or lockfile changes.
- Docs/ledger: both product and platform evidence are preserved through the G4 candidate plus this G5 ledger.

## 4. G5 Delta Beyond G4-R1

Diff from G4-R1 evidence tip to G5 repair tip:

- ai-ledger/platform/2026-07-09_product_merge_prep_g2_r2_regression_repair.md
- backend/api/v1/platform/health.py
- backend/tests/test_route_authorization_policy.py
- backend/tests/test_s6e_rbac_permission_registry_drift_gate.py

There is no frontend diff between G4-R1 and G5.

## 5. Validation

### Backend Targeted Gates

Command:

```text
poetry run pytest tests/test_platform_p10_contracts.py tests/test_platform_p17_registry.py tests/test_platform_p22_controlled_execution.py tests/test_platform_p22e3_backup_check_source_probe.py tests/test_platform_p22g_governed_backup_check.py tests/test_route_authorization_policy.py tests/test_platform_p11c0_legacy_guard.py tests/test_s6e_rbac_permission_registry_drift_gate.py
```

Result: 408 passed, 0 failed.

This proves the G2-R2 D-class regression repairs are present in G5.

### Alembic

Command:

```text
poetry run alembic heads
```

Result: 030_platform_backup_status_source (head).

### Frontend

G5 attempted a fresh pnpm run build in the new worktree. The local install was blocked by the active pnpm supply-chain policy:

```text
ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION: node-releases@2.0.51 was published within the minimumReleaseAge cutoff.
```

This is classified as an environment/supply-chain timing blocker for local re-run, not a code failure. G5 made no frontend changes relative to the G4-R1 evidence tip. The accepted G4-R1 evidence for the same frontend tree remains:

- frontend build passed
- frontend tests passed
- real-stack smoke passed with 19/19 HTTP 200 and 0 backend 5xx

### Static Gates

- git diff --check: passed.
- GitNexus analyze: repository indexed successfully, 12,355 nodes, 37,469 edges, 790 clusters, 300 flows before the G5 repair commit.
- GitNexus status after G5 repair: stale, as expected after the repair commit; re-analysis is required after the final G5 ledger commit.

## 6. A/B/C/D Classification

| Category | Count | Notes |
| --- | ---: | --- |
| A product pre-existing | 0 | No product pre-existing failure in targeted G5 gates. |
| B platform pre-existing | 0 | No platform pre-existing failure in targeted G5 gates. |
| C environment/infrastructure | 1 | Local pnpm install blocked by minimumReleaseAge for node-releases@2.0.51. |
| D merge-introduced regression | 0 | G2-R2 D-class suite passed after restoring the G2-R2 repair commit. |

## 7. Risk and Blockers

Risk: medium due to large cross-track merge, but G5 made no new feature changes and preserved the G4-reviewed candidate. The only G5 code delta restores the already-reviewed G2-R2 route-policy and RBAC drift repair.

Blockers: none for CTO product promotion. The local frontend rebuild could not be repeated because of supply-chain age policy, but G5 has no frontend delta relative to the G4-R1 candidate that already passed frontend build, frontend tests, and real-stack smoke.

## 8. Final Verdict

PASS_FOR_CTO_PRODUCT_PROMOTION.

This G5 branch is a delivery-candidate product branch. It must not be pushed to product-dev-recovered without explicit CTO approval.
