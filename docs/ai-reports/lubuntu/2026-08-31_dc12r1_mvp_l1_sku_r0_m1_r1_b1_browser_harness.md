# DC-12R1-MVP-L1-SKU-R0-M1-R1-B1 — Authoritative Browser Harness Authoring

**Date:** 2026-08-31 | **Branch:** `codexl/dc12r1-mvp-l1-sku-r0-m1-r1-b1-browser-harness-2026-08-31` @ base `5c5a9a82a3a2f7f0d5471c38b204e76bac91745e`
**Verdict: STOP_AND_REPORT_CTO_WITH_EXACT_SKU_PRODUCT_OR_HARNESS_DEFECT**

## Verdict summary

The frozen SKU browser harness (`sku-m1-browser/`) is authored, self-contained,
and passes every author gate: exact two-node manifest, deterministic node
identities, real-API provisioning only, static fail-closed validator GREEN,
TypeScript compile clean, Playwright list = exactly 4 executions (2 nodes ×
2 viewports), and all 10 mutation gates RED with byte-identical restores.
During the labeled `AUTHOR_DIAGNOSTIC_ONLY` runs a **CURRENT_PRODUCT_DEFECT**
was found and confirmed deterministic (4 reproductions): **PUT
`/api/v1/catalog-products/{id}` (catalog product rename) returns HTTP 500** —
`sqlalchemy.exc.MissingGreenlet` raised in `backend/api/v1/catalog_products.py::_to_read`
during response serialization. CATALOG-HIST-001 requires exactly this rename
step, so the harness cannot progress past step 3 of that node. Per task
discipline the product is NOT repaired in B1; this report stops with the exact
defect below.

## 1. Exact CURRENT_PRODUCT_DEFECT

| Field | Value |
|---|---|
| Browser step | CATALOG-HIST-001, step 3 "Rename the source CatalogProduct" (blocks steps 3–10 of the node) |
| Request | `PUT /api/v1/catalog-products/{product_id}`, JSON body `{"name": "<new name>"}`, `Authorization: Bearer <contextual wholesaler JWT>` — body is exactly the `CatalogProductUpdate` schema |
| Response | HTTP **500**, text body `Internal Server Error` (unhandled ASGI exception) |
| Root cause (sanitized) | `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call await_only()` raised at `backend/api/v1/catalog_products.py:40` inside `_to_read()` — the response serializer triggers a lazy relationship load (`sellable_units`) on the product instance after `CatalogProductService.update_product` has mutated it, outside the async greenlet |
| Affected product path | `backend/api/v1/catalog_products.py` (`update_catalog_product` route + `_to_read`), `backend/services/catalog_product_service.py` (`update_product`) |
| Determinism | Reproduced 4× (2 browser diagnostic runs + 2 direct API probes) on a fresh PG16 stack at the exact base candidate |
| Provenance | The catalog-products API (route + serializer) is new in the SKU candidate lineage (introduced by `8bdb9911`/`8cef1fff`); no backend test exercises the rename route against a real async database, which is why the A3 zero-red authority run did not surface it |

Secondary unclassified observation (not a defect claim): during browser-run
bursts, isolated GETs (`/api/v1/inventory/stocks/{code}`, catalog list) were
sporadically answered `401 UNAUTHENTICATED` and then succeeded on replay with
the identical token minutes later (token TTL had ~25 min remaining). The
harness now embeds exact status/body in its failure messages so the
independent run can classify this (rate-limit/auth-middleware interaction vs
harness).

## 2. Deliverables (all inside the isolated `sku-m1-browser/`)

| Deliverable | File |
|---|---|
| Frozen Playwright harness | `playwright.config.ts` (desktop 1280×800 + mobile-390 390×844 Chromium, retries 0, workers 1), `tests/catalog-id-001.spec.ts`, `tests/catalog-hist-001.spec.ts` |
| Exact node manifest | `manifest/nodes.manifest.txt` (2 sorted unique LF lines) |
| Static validator | `validator/static_validator.py` (stdlib) |
| Mutation suite | `validator/mutations.py` (10 mutations + pristine/restore controls) |
| Execution runbook | `README.md` |
| Reconciliation schema | `manifest/reconciliation.schema.json` (+ builder `src/reconcile.ts`) |
| Sanitized artifact scanner | `tools/scan_artifacts.py` |
| Source/harness path accounting | `inventory/source-path-accounting.md` |
| Browser-authoring report | this file |
| Independent verifier handoff | `README.md` §9 (verifier executes the runbook; B1 runs are `AUTHOR_DIAGNOSTIC_ONLY`) |
| Provisioning data | `provisioning/official.json` (missing keys → PRECONDITION_FAIL) |
| Local SMTP sink | `tools/smtp_sink.py` (stdlib AUTH-LOGIN Maildir sink; local fake only) |
| Frozen install | `package.json` + `pnpm-lock.yaml` (`@playwright/test` 1.49.1, `typescript` 5.7.3) |

## 3. Runtime authenticity

Real PG16.15 + Redis 7 (DB15) + real backend process (uvicorn, production email
mode with SMTP pointed at the harness's local Maildir sink) + real
production-built frontend (`vite build`, `VITE_API_URL` build-time config,
served over HTTPS with a self-signed cert) + real system Chromium through
Playwright. No API response mocks, no route fulfillment/interception, no direct
database rows for preconditions: tenants, owner credentials, catalog product,
two sellable-unit packages, per-unit inventory stock, retailer invitation,
registration, credentials, binding and prices are all created through accepted
public API flows (signup → verify-email → setup-credential → login →
select-tenant → catalog-products → inventory/adjust → invitations →
retailers/register → retailers/setup-credential → client/auth/login →
pricing/prices). Passwords live only in `provisioning/official.json` and are
scan-gated out of artifacts.

## 4. Author validation results

| Gate | Result |
|---|---|
| Frozen dependency install (`pnpm install --frozen-lockfile`) | OK |
| `playwright test --list` | exactly 4 executions: `[desktop]/[mobile-390] × CATALOG-ID-001/CATALOG-HIST-001` |
| Static validator | GREEN (manifest exactness, anchors, no-mock, nav allowlist, H2-C ban, DB-seed ban, viewport coverage) |
| TypeScript compile (`tsc --noEmit`, strict) | clean |
| Harness truth/contract enforcement | validator enforces: exact manifest, deterministic titles (dynamic-title guard), desktop+390px projects, passive-observation only, no response mocking, no H2-C imports, no DB drivers/seed statements, payload-binding anchor, forged/cross-tenant rejection anchors, immutable-snapshot anchor, reconciliation accounting (gap=0), artifact scan |
| Mutation suite | **all 10 mutations RED as intended** (payload assertion, mismatch rejection, cross-tenant rejection, independent stock, immutable snapshot, unavailable item, 390px coverage, no-mock guard, supported-navigation guard, manifest exactness) — each with byte-identical restore verified by SHA-256 and post-restore GREEN |

## 5. AUTHOR_DIAGNOSTIC_ONLY runs (not independent authority)

Labeled runs against the full real stack (fresh PG16, Redis 7 DB15 empty +
sentinel unreachable, alembic head exactly `038_catalog_identity_vertical_slice`
with parent 037, backend production-email mode, production-built frontend,
system Chromium):

| Node | Progressed through | Blocked at |
|---|---|---|
| CATALOG-HIST-001 (desktop) | order created via public API with stable `sellable_unit_id` (201); historical UI capture | **rename → 500 (the defect, §1)** |
| CATALOG-ID-001 (desktop) | wholesaler UI sign-in; product + 2 packages created through the SKU UI; catalog-list verification; distinct-UUID proof | inventory stocks GET → transient 401 (unclassified observation, §1) |

Harness-side defects found and fixed during authoring (harness files only):
SMTP sink hardening (AUTH-LOGIN state machine, self-healing Maildir), email
quoted-printable decoding + fragment tokens, kind-aware consume-once mail
selection, `select-tenant` binding (`available_tenants[].id`), retailer
price preconditions, `baseURL` + absolute backend-origin API calls, portal
handoff entry `/client/login?w=<code>` recognized as supported navigation.
After every harness fix the static validator, tsc, and the full mutation gate
were re-run GREEN.

## 6. Required explicit statements

```
H2-C_NOT_EVALUATED
A3_BACKEND_AUTHORITY_REUSED_ONLY_BY_EXACT_ANCESTRY
BROWSER_RESULT_NOT_INDEPENDENT
PRICING_NOT_STARTED
ORDER_PRICE_NOT_STARTED
REORDER_NOT_STARTED
```

Notes: H2-C paths were never read, copied, modified or executed. The A3
backend authority result applies only through the exact ancestry
(`24a28d76 → 8bdb9911 → 8cef1fff → 0376ce93 → 5c5a9a82`); B1 adds no backend
authority of its own. No browser verdict in this report is an independent
authority. The retailer *price precondition* used by provisioning is the
existing phase-3 `retailer_prices` mechanism, not the PRICING track.

## 7. CTO hand-off

1. **Product defect (blocks CATALOG-HIST-001):** repair the rename endpoint
   (`PUT /api/v1/catalog-products/{id}` → 500 MissingGreenlet,
   `backend/api/v1/catalog_products.py::_to_read` lazy-load during update
   response). Detail in §1. Repair belongs to the product owner, not B1.
2. After the repair, B1's frozen harness is ready for the independent
   verifier: execute `sku-m1-browser/README.md` on a fresh stack; the two
   nodes must reach gap=0 reconciliation across desktop and mobile-390.
3. Classify the sporadic in-run `401 UNAUTHENTICATED` observation (§1) using
   the harness's embedded status/body diagnostics.
