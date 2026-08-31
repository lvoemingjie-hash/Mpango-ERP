# B1 source/harness path accounting

## Files added by B1 (all inside `sku-m1-browser/` — the isolated harness)

| Path | Purpose |
|---|---|
| `sku-m1-browser/package.json` | frozen harness-only dependencies (`@playwright/test` 1.49.1, `typescript` 5.7.3, `@types/node` 22.10.5); no dependency outside this directory is changed |
| `sku-m1-browser/tsconfig.json` | strict TS compile (typecheck gate) |
| `sku-m1-browser/playwright.config.ts` | frozen node identities, two viewport projects (desktop 1280x800, mobile-390 390x844), retries 0, workers 1 |
| `sku-m1-browser/manifest/nodes.manifest.txt` | exact two-node manifest (sorted, unique, LF) |
| `sku-m1-browser/manifest/frozen-candidate.sha` | frozen candidate SHA binding for preflight |
| `sku-m1-browser/manifest/reconciliation.schema.json` | reconciliation contract (4 combinations, gap must be 0) |
| `sku-m1-browser/provisioning/official.json` | official provisioning data (missing => PRECONDITION_FAIL) |
| `sku-m1-browser/src/global-setup.ts` | fail-closed preflight + provisioning entry (VOID/PRECONDITION_FAIL => 0 browser launches) |
| `sku-m1-browser/src/preflight.ts` | candidate SHA, alembic head/parent, live Redis authority, sentinel, backend/frontend health |
| `sku-m1-browser/src/provision.ts` | public-API provisioning only (signup/verify/setup-credential/login/select-tenant/catalog/inventory/retailer) |
| `sku-m1-browser/src/observe.ts` | passive network observation (no route interception) |
| `sku-m1-browser/src/reconcile.ts` | node x viewport reconciliation builder (gap must be 0) |
| `sku-m1-browser/tests/catalog-id-001.spec.ts` | frozen node CATALOG-ID-001 |
| `sku-m1-browser/tests/catalog-hist-001.spec.ts` | frozen node CATALOG-HIST-001 |
| `sku-m1-browser/validator/static_validator.py` | static fail-closed validator (manifest, anchors, no-mock, nav allowlist, H2-C ban, DB-seed ban) |
| `sku-m1-browser/validator/mutations.py` | 10 mutations + pristine/restore controls |
| `sku-m1-browser/tools/smtp_sink.py` | local SMTP->maildir sink (stdlib only) |
| `sku-m1-browser/tools/scan_artifacts.py` | sanitized artifact scanner |
| `sku-m1-browser/README.md` | execution runbook + independent verifier handoff |
| `sku-m1-browser/results/.gitignore` | run outputs never enter the repository |

## Files modified by B1

| Path | Change |
|---|---|
| `docs/ai-reports/lubuntu/2026-08-31_dc12r1_mvp_l1_sku_r0_m1_r1_b1_browser_harness.md` | browser-authoring report (added) |
| `ai-ledger/product-ai/2026-08-31_dc12r1_mvp_l1_sku_r0_m1_r1_b1_browser_harness.md` | B1 ledger entry (added) |

## Files NOT touched (verified)

`backend/**` product code and tests, `frontend/**` product code, `alembic/**`,
A3 evidence (`docs/ai-reports/lubuntu/2026-08-31_dc12r1_mvp_l1_sku_r0_m1_r1_a3_*`),
`j1h2b-forgot-reset/**` and every H2-C path, pricing/order/reorder product code.
