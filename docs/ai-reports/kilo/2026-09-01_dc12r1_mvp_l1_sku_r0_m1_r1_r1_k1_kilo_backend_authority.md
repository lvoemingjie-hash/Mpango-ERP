# DC-12R1-MVP-L1-SKU-R0-M1-R1-R1-K1 — Kilo Independent Review and Backend Authority

**Date:** 2026-09-01/02 (run window 2026-09-01 21:50 → 2026-09-02 07:05 CST)
**Product candidate:** `c2c3bff38514901d7d3f7d71bb49af6d6eb4226b` (exact, detached)
**Source branch:** `origin/zcode/dc12r1-mvp-l1-sku-r0-m1-r1-r1-multipackaging-closure-2026-09-01`
**Reference-only author report (NOT used as authority):** `f05b9c0a42b73cba401746dd89ac90214d5656f6`
**New report-only branch (this task):**
`reports/dc12r1-mvp-l1-sku-r0-m1-r1-r1-k1-kilo-backend-authority-2026-09-01` @ base `c2c3bff3`

## VERDICT

```
STOP_AND_REPORT_CTO_WITH_EXACT_SKU_R1_PRODUCT_OR_AUTHORITY_DEFECT
```

One **CURRENT_PRODUCT_DEFECT** was found by independent P1 review (**F-1**). Every
other independent claim passed, and the single-launch full backend authority is
green with accounting gap = 0, so the authority itself carries no product defect.
The stop is driven by F-1 alone.

Exact defect (§3 / F-1): `GET /api/v1/client/products/{product_id}` returns
**HTTP 500 `INTERNAL_SERVER_ERROR`** — and echoes SQLAlchemy/asyncpg driver text
into the response body — for two non-canonical UUID path forms
(`{550e8400-…-446655440000}` and `urn:uuid:550e8400-…-446655440000`), where the
R1 contract and the module's own docstring require a clean **404
`PRODUCT_NOT_FOUND`**. Root cause: `backend/api/v1/client/products.py:238-244`
validates with `UUID(str(product_id))`, which accepts `{…}` / `urn:uuid:…` forms,
and then binds the **original non-canonical string** to the `uuid` column at
line 255, so the "fail closed before any SQL" guard does not fail closed.

---

## 1. Candidate verification

| Check | Result |
|---|---|
| `git fetch origin zcode/…-multipackaging-closure-2026-09-01` → tip | `f05b9c0a42b73cba401746dd89ac90214d5656f6` ✔ |
| `f05b9c0a` parent | `c2c3bff38514901d7d3f7d71bb49af6d6eb4226b` (exact) ✔ |
| `f05b9c0a` is report-only | `git diff --name-status c2c3bff3 f05b9c0a` → `A docs/ai-reports/windows/2026-09-01_dc12r1_mvp_l1_sku_r0_m1_r1_r1_multipackaging_closure.md` only; numstat `+380 / -0` ✔ |
| Detached clean worktree at exact candidate | `/home/ivy/Documents/Codex/kilo-r1-k1/candidate-c2c3bff3`, `HEAD=c2c3bff38514901d7d3f7d71bb49af6d6eb4226b`, `git status --porcelain` = 0 at creation ✔ |
| Ancestry `a45fe99e → c2c3bff3` | `git merge-base --is-ancestor a45fe99eaab73f4949cf4c3e4797626ec5f571cd c2c3bff38514901d7d3f7d71bb49af6d6eb4226b` → yes; `git rev-list --count a45fe99e..c2c3bff3` = **1** ✔ |
| `git diff --check` (a45fe99e..c2c3bff3) | clean, exit 0, no whitespace/EOF errors ✔ |
| Secret scan of the diff | no match for private keys, `AKIA…`, `sk-…`, or `password/secret/api_key = "…"` patterns ✔ |

### 1.1 Changed paths — `git diff --name-status a45fe99e c2c3bff3` (20 paths)

```
M  backend/.hypothesis/unicode_data/15.0.0/codec-utf-8.json.gz   (binary cache, see F-3)
M  backend/api/v1/client/products.py                     (+187 / -136)
M  backend/schemas/client.py                             (+46  / -26)
M  backend/services/catalog_product_service.py           (+8   / -2)
M  backend/services/import_service.py                    (+4   / -1)
A  backend/services/sku_integrity.py                     (+93  / -0)
M  backend/services/sku_service.py                       (+6   / -1)
A  backend/tests/test_sku_r1_client_catalog_contract.py  (+433 / -0)
A  backend/tests/test_sku_r1_multipackaging_closure.py   (+468 / -0)
M  frontend/src/pages/client/CreateOrderPage.tsx         (+42  / -34)
M  frontend/src/pages/client/ProductDetailPage.tsx       (+131 / -65)
M  frontend/src/pages/client/ProductListPage.tsx         (+38  / -13)
A  frontend/src/tests/ClientMultipackaging.test.tsx      (+196 / -0)
M  frontend/src/types/client.ts                          (+17  / -5)
M  sku-m1-browser/README.md                              (+1   / -1)
M  sku-m1-browser/tests/catalog-hist-001.spec.ts         (+13  / -6)
M  sku-m1-browser/tests/catalog-id-001.spec.ts           (+66  / -9)
M  sku-m1-browser/validator/mutations.py                 (+37  / -1)
M  sku-m1-browser/validator/static_validator.py          (+10  / -0)
```

**No migration / no schema change.** Filtering the changed-path set for
`alembic|migration|schema|sql` matches only `backend/schemas/client.py` — a
Pydantic response-model module, not a database migration. No file under
`backend/alembic/versions/` is touched; the chain still has exactly one head,
`038_catalog_identity_vertical_slice`, with parent
`037_payment_declarations_schema` (verified by the runner's R3-A1 alembic
authority, §8).

---

## 2. Fresh infrastructure (no ZCODE reuse)

| Resource | Value |
|---|---|
| Docker network | `kilo_r1_k1_net` (bridge, new) |
| PostgreSQL | container `kilo_r1_k1_pg16`, image `postgres:16-alpine`, `127.0.0.1:18830` |
| Redis | container `kilo_r1_k1_redis7`, image `redis:7-alpine`, `127.0.0.1:18831` |
| PG roles | `mpango_super` (rolsuper=t, provisioning only) · `k1_auth` (**rolsuper=f, rolcreatedb=t, rolcreaterole=t**) — the runner's TEST_DATABASE_URL role |
| Databases (all owned by `k1_auth`, all created empty) | `test_k1_probe`, `test_k1_focus_a`, `test_k1_focus_b`, `test_k1_authority` |
| Alembic | real `alembic upgrade head` from empty database, run as `k1_auth`, on each of the four databases; `alembic current` = `038_catalog_identity_vertical_slice (head)` on all four; logs in `artifacts/alembic-*.log` |
| Redis authority | `PW1R3_TEST_REDIS_URL = redis://127.0.0.1:18831/15`; `DBSIZE`=0 before and after; sentinel `127.0.0.1:26379` has **0** listeners (unreachable) ✔ |
| Python | new venv `/home/ivy/Documents/Codex/kilo-r1-k1/.venv-k1` (Python 3.12.3), built from `backend/requirements.txt` + `pytest==8.4.2`, `pytest-asyncio==0.26.0`, `hypothesis==6.150.2`, `httpx==0.28.1`, `pytest-cov==4.1.0`, `psycopg==3.2.3` |
| SMTP | no SMTP was required by any executed node; nothing read `.env.prod` (the backend conftest only reads `backend/.env.test`, `backend/.env`, `.env` via `setdefault`; none of those exist in the candidate) |
| Not reused | no ZCODE container, volume, network, database, venv, worktree or artifact was used. The pre-existing running containers `sku_m1_a5_pg16` / `sku_m1_a5_redis7` (ports 15449 / 16449) were left untouched and never referenced. |

**ZCODE author evidence was not used as authority.** The author report was
touched only through `git diff --name-status` / `--numstat` to prove it is
report-only (§1); its content was never opened, and no ZCODE artifact,
manifest, JUnit file, container or database was read or reused.

---

## 3. Independent P1 review — claim by claim

Method: **code inspection** of `backend/api/v1/client/products.py`,
`backend/schemas/client.py`, `backend/api/v1/client/dependencies.py`,
`backend/api/context/*` **plus fresh-runtime API probes** against the real
FastAPI app (ASGI transport, real JWT retailer login, real PostgreSQL 16, two
provisioned tenants via `TenantProvisioningService`). Probe sources live
**outside** the candidate worktree (`/home/ivy/Documents/Codex/kilo-r1-k1/probes/`);
no product, test, migration, frontend or harness file was edited.

Probe artefacts: `artifacts/p1-probe-summary.json`, `artifacts/p1-probe.log`,
`artifacts/p1-malformed-ids.json`, `artifacts/p1-defect-http.json`,
`artifacts/p1-defect-server-log.txt`.

| # | P1 claim | Evidence | Result |
|---|---|---|---|
| 1 | List/count/pagination operate on CatalogProduct, not SKU rows | list runs 3 product-domain SQL: `COUNT(*) FROM catalog_products p`, `SELECT p.id FROM catalog_products p …`, then one unit-row query; `total` counts products (7 two-unit products → `total=7`, never 14) | **PASS** |
| 2 | One product with two units → `total=1` and one item with `units[2]` | probe `P1-2`: `total=1`, `len(items)=1`, `unit_count=2`, `len(units)=2`, container `id` == CatalogProduct id | **PASS** |
| 3 | Page boundaries cannot duplicate or omit products due to unit joins | `P1-3`: corpus of 7 products × 2 units, enumerated at `size` ∈ {1,2,3,5}: collected=7, unique=7, dupes=0, `total=7`, every item carried exactly 2 units — no inflation, no omission | **PASS** |
| 4 | Product detail queries `CatalogProduct.id` only | `P1-4` (200, container id matches, 2 units) + captured SQL is `SELECT … FROM catalog_products p WHERE p.id = $1` — `skus` is only joined, never filtered by id | **PASS** |
| 5 | A `sellable_unit_id` used as `product_id` returns clean 404 | `P1-5`: both unit UUIDs of a 2-unit product → `404 / PRODUCT_NOT_FOUND` | **PASS** |
| 6 | Malformed IDs return clean 404 without unexpected SQL/errors | `P1-6`: 19 probes (non-UUID text, `''`, `1`, `null`, 300-char, `';DROP TABLE …'`, `../../etc/passwd`, `%27%20OR%201=1--`, 32-hex no-dash, uppercase, plus `page=0/-1/abc`, `size=0/101/abc`) → all 404/422, zero 500. **But see F-1**: 3 further forms return 500. | **PASS on the clean set / FAIL overall (F-1)** |
| 7 | Only active products and active units are exposed | `P1-7` inactive unit absent from `units`; `P1-7b` inactive product absent from list and `PRODUCT_INACTIVE` 404 on detail (SQL carries `s.is_active = true`, `s.is_deleted IS NOT TRUE`, `p.is_active = true`, `p.is_deleted IS NOT TRUE`, and `EXISTS(active unit)`) | **PASS** |
| 8 | Tenant / retailer-specific price / RBAC isolation intact | tenant isolation from `SET LOCAL search_path TO "<tenant_schema>", public` (`api/context/tenant.py:73`); `P1-8/8b` cross-tenant read → 404/empty; `P1-8c` second retailer in the same tenant sees `price=None`, `can_order=false` while the bound retailer sees `25.50 / 240.00`; `P1-8d` unauthenticated → 401; `P1-8e` tenant user without `retailer_operator` → 401 `INVALID_CREDENTIALS`; `retailer_id` is resolved server-side from the binding, never from the request | **PASS** |
| 9 | Query count bounded, no N+1 | `P1-9`: 7 products → 3 product-domain SQL; 21 products → **also 3** product-domain SQL (total per-request SQL flat at 8 both times); `P1-9b` detail → 2 product-domain SQL (total 7 incl. auth/RBAC). No per-product or per-unit query growth. | **PASS** |
| 10 | Ordering of products and units is deterministic | units `ORDER BY s.package_quantity ASC, s.sku_code ASC, s.id ASC`; products `ORDER BY p.name ASC, p.id ASC`; `P1-10` unit keys sorted; `P1-10b` 5 consecutive list calls returned byte-identical, name-ascending order | **PASS** |

**Claim accounting: 19/19 probe claims PASS** (`claims=19 passed=19 failed=0`).
Claim 6 is nevertheless **not satisfied** because of F-1 below.

### F-1 — CURRENT_PRODUCT_DEFECT: non-canonical UUID path ids → HTTP 500 (not 404)

Deterministic reproduction (3/3 repetitions each, `artifacts/p1-malformed-ids.json`,
`artifacts/p1-defect-http.json`):

```
GET /api/v1/client/products/{550e8400-e29b-41d4-a716-446655440000}   -> 404 PRODUCT_NOT_FOUND
GET /api/v1/client/products/%7B550e8400-e29b-41d4-a716-446655440000%7D -> 500 INTERNAL_SERVER_ERROR
GET /api/v1/client/products/urn:uuid:550e8400-e29b-41d4-a716-446655440000
                                                                     -> 500 INTERNAL_SERVER_ERROR
```

Sanitized server-side exception metadata (no credentials, no tenant data):

```
sqlalchemy.exc.DBAPIError: (sqlalchemy.dialects.postgresql.asyncpg.Error)
<class 'asyncpg.exceptions.DataError'>: invalid input for query argument $1:
'{550e8400-e29b-41d4-a716-446655440000}' (invalid UUID
'{550e8400-e29b-41d4-a716-446655440000}': length must be between 32..36 characters, got 38)
[SQL: SELECT id, name, description, category, is_active
      FROM catalog_products p WHERE p.id = $1 AND p.is_deleted IS NOT TRUE]
```

HTTP 500 body (driver text is disclosed to the caller):

```json
{"code":"INTERNAL_SERVER_ERROR",
 "message":"DBAPIError: (sqlalchemy.dialects.postgresql.asyncpg.Error)
 <class 'asyncpg.exceptions.DataError'>: invalid input for query argument $1: …"}
```

Root cause — `backend/api/v1/client/products.py`:

```python
236    # Fail closed on malformed ids before any SQL (a non-UUID path id can
237    # never match catalog_products.id).
238    try:
239        UUID(str(product_id))            # accepts "{…}" and "urn:uuid:…" forms
...
255            {"product_id": product_id},  # <-- ORIGINAL non-canonical string bound to uuid
```

`uuid.UUID()` accepts the brace and `urn:uuid:` forms per its documented
grammar, so the guard admits them and SQL is executed; asyncpg then rejects the
38/45-character literal. The guard therefore does not deliver the behaviour its
own comment and the module docstring (lines 17-19, 236-237) claim.

Impact / classification: **CURRENT_PRODUCT_DEFECT**. Reachable by any
authenticated retailer on the catalog browse path; the specified outcome is 404,
the observed outcome is 500 plus driver-error disclosure. It is *not* an
injection, data leak of tenant data, or ordering defect — parameter binding is
used throughout — but it is a product defect on a claim this review is required
to prove, and per the directive it forces `STOP_AND_REPORT_CTO`.

Note on origin: the pre-R1 code (`a45fe99e:backend/api/v1/client/products.py`,
`WHERE s.id = :product_id`, no validation) returned 500 for *every* malformed
id, so R1 is a strict improvement. R1 nevertheless advertises "fail closed on
malformed ids before any SQL" and leaves a 500 for two forms, so the defect
stands in the candidate. The candidate's own regression test covers only
`"not-a-uuid"`, which is why it was not caught.

Minimal fix (not applied — outside this task's hard scope): parse to a canonical
UUID and bind the canonical value, e.g. `canonical = UUID(str(product_id));
product_uuid = str(canonical)` and pass `product_uuid`; that turns both forms
into the specified 404 (no row matches) with no SQL error.

---

## 4. Independent frontend / oracle review

| # | Claim | Evidence | Result |
|---|---|---|---|
| 1 | One visible card/container per CatalogProduct | `ProductListPage.tsx` renders one `<Link data-testid="client-product-card" key={product.id}>` per list item; list items are products (§3 cl.1/2). Vitest F1 asserts `findAllByTestId('client-product-card')` has length **1** for a 2-unit product. | **PASS** |
| 2 | Both packaging options contained in that same product | `client-product-units` `<ul>` is rendered **inside** the same card container and maps `product.units`; Vitest F1 asserts the container's units node contains both `JUICE-BTL` and `JUICE-CASE`. | **PASS** |
| 3 | Accessible desktop/mobile packaging selection | `role="radiogroup"` + `aria-label="Packaging"`, children `role="radio"` with `aria-checked` and `data-sellable-unit-id`, CSS grid `grid-cols-2` (responsive) + focus ring. Vitest F2 resolves `getByRole('radiogroup', {name:'Packaging'})` and `within(group).getByRole('radio', {name:/JUICE-CASE/})`. Observation only (not a defect): arrow-key roving focus is not implemented; each option is a real `<button>`, so Tab + Enter/Space operation works. | **PASS** |
| 4 | Price, stock, subtotal and `can_order` follow the selected unit | `ProductDetailPage` derives everything from `selectedUnit`: price block (`formatKES(selectedUnit.price)`), badge `STOCK_BADGE[selectedUnit.stock_level]` (`data-testid="selected-unit-stock"`), subtotal `selectedUnit.price * quantity`, order block gated on `product.can_order && selectedUnit?.can_order`. Vitest F2: `KES 25.50 / Limited Stock` → click case → `KES 289.00 / In Stock`. | **PASS** |
| 5 | The real submission carries the selected `sellable_unit_id` UUID | `handleAddToOrder` navigates with `sellable_unit_id: selectedUnit.sellable_unit_id`; `CreateOrderPage.addUnit(product, unit)` sets `sellable_unit_id: unit.sellable_unit_id`. Vitest F3 captures the real `POST /client/orders` body: `items[0].sellable_unit_id === CASE_ID` (the selected unit) and `sku_code === 'JUICE-CASE'`. | **PASS** |
| 6 | Browser oracle validates containment + submitted/returned UUID, not merely two SKU links | `catalog-id-001.spec.ts` now asserts: `productContainer` `toHaveCount(1)`; `containerUnits` contains **both** codes; `data-selected-sellable-unit-id` switches `bottleUuid → caseUuid`; `selected-unit-stock` text changes `Low Stock → Limited Stock`; order payload UUIDs match `/^[0-9a-f-]{36}$/i`; and `orderItems[0].sellable_unit_id === bottleUuid` (returned identity equals the chosen unit). `static_validator.py` adds a **forbidden** pattern `getByRole\('link',\s*\{\s*name:\s*new RegExp\(skuCode` so per-SKU link locators (the old two-links proof) cannot come back. | **PASS** |
| 7 | No pricing or order-price semantics introduced | changed-path set contains no pricing/order-price module; the frontend diff only selects which unit's already-existing `price` is displayed and forwards the existing `sellable_unit_id`; no new price field, no price computation, no order-price logic (`formatCurrency`/`formatKES` are display-only). | **PASS** |

Independent execution of the candidate's own UX oracle (fresh `pnpm install
--frozen-lockfile`, jsdom, no browser):

```
npx vitest run src/tests/ClientMultipackaging.test.tsx   -> 3 passed (3)  [F1, F2, F3]
npx tsc -p tsconfig.app.json --noEmit                    -> clean (rc=0)
sku-m1-browser: python3 validator/static_validator.py --allow-missing-reconciliation -> STATIC VALIDATOR: GREEN
sku-m1-browser: python3 validator/mutations.py -> all 42 mutations RED as intended
                (M37-M42 new R1 oracle mutations RED), pristine and restored states GREEN
```
The mutation run is a **static** oracle gate; no Playwright/browser execution
was performed (see required statements).

---

## 5. Independent P2 review — claim by claim

### 5.1 Code inspection of all four SKU insertion paths

| Path | Call site | Guarded flush |
|---|---|---|
| 1. `CatalogProductService.create_product` | `services/catalog_product_service.py:92` (POST /catalog-products) | `await flush_skus_or_409(db, sku_code=request.sellable_units[0].sku_code)` |
| 2. `CatalogProductService.add_sellable_unit` | `services/catalog_product_service.py:187` (POST /catalog-products/{id}/sellable-units) | `await flush_skus_or_409(db, sku_code=request.sku_code)` |
| 3. `SKUService.create_sku` | `services/sku_service.py:90` (`db.add(sku)` + guarded flush + `db.refresh`) | `await flush_skus_or_409(db, sku_code=sku_code)` |
| 4. `ImportService.apply` | `services/import_service.py:568` (bulk import) | `await flush_skus_or_409(db, sku_code=sku_code)` |

`services/sku_integrity.py:77-93` — the guard catches `IntegrityError` at
**flush** (i.e. inside the transaction, at the `INSERT`, which is exactly where
the database race surfaces), performs `await db.rollback()` **before** raising,
and only then, if `is_sku_code_unique_violation(exc)` is true, raises
`HTTPException(409, {"code":"SKU_EXISTS", …})`; otherwise it re-raises the
original `IntegrityError`. Rollback therefore happens before the session is
returned or reused, and it happens for **every** `IntegrityError`, not only the
mapped one (so an unrelated violation also leaves a clean session).

### 5.2 Synchronized real two-session races

Probe: `/home/ivy/Documents/Codex/kilo-r1-k1/probes/p2_race_probe.py` (outside
the worktree). Two **separate `AsyncSession`s on two separate pooled
connections**, both bound to the same real tenant schema.

* **natural mode** — both sessions run the whole public service path
  concurrently from a start gate (10 iterations per path).
* **ordered mode** — instrumented barriers force the deterministic interleaving
  that the natural mode only reaches probabilistically: both friendly prechecks
  complete **before** either `INSERT`, then session 1 `INSERT`s (uncommitted),
  session 2 `INSERT`s (blocks on the unique index), session 1 `COMMIT`s,
  session 2's `INSERT` raises. The instrumentation also records the guard-call
  sequence, which proves the 409 is produced by the guarded flush and not by
  the friendly precheck (`guard_calls` ≥ 2 in all 80 ordered races).

10 iterations × 4 paths × 3 configurations = **120 races**. Artefacts:
`artifacts/p2-race-summary.json` (all 120 race records),
`artifacts/p2-exception-metadata.json`, `artifacts/k1-p2-final.out`.

| Path | natural (10) | ordered, winner=a (10) | ordered, winner=b (10) |
|---|---|---|---|
| `create_product` | 0 violations (a won 10, b won 0) | 0 violations (a 10 / b 0) | 0 violations (a 0 / b 10) |
| `add_sellable_unit` | 0 violations (a 10 / b 0) | 0 violations (a 10 / b 0) | 0 violations (a 0 / b 10) |
| `create_sku` | 0 violations (a 10 / b 0) | 0 violations (a 10 / b 0) | 0 violations (a 0 / b 10) |
| `import_apply` | 0 violations (a 9 / b 1) | 0 violations (a 10 / b 0) | 0 violations (a 0 / b 10) |

Every race satisfied **all four** required properties: exactly one `success`,
exactly one `SKU_EXISTS/409`, **zero 500 / zero leaked `IntegrityError`**,
exactly **one** persisted SKU row, and the losing **session object** was
immediately reusable (a fresh product was created and committed through it after
the 409). Both winner orders were exercised 10× each per path — **60 races with
`a` winning and 60 with `b` winning**, all deterministic.

**Rollback scope proven:** after each race the parent `CatalogProduct` count for
the raced name is 1 (not 2), i.e. the loser's whole transaction — parent product
included — was rolled back, not just the SKU insert.

### 5.3 Constraint identification — sanitized exception metadata

`artifacts/p2-exception-metadata.json` (captured on real PG16 through the real
guard):

| Violation | sqlstate | `orig.constraint_name` | `diag.constraint_name` | classified SKU-code | outcome |
|---|---|---|---|---|---|
| duplicate `sku_code` | `23505` | `None` | `None` | **True** | `409 SKU_EXISTS` |
| `ck_skus_package_quantity_positive` (`package_quantity = 0`) | `23514` | `None` | `None` | **False** | `IntegrityError` propagates unchanged (**not** 409) |
| not-null `sku_code` | `23502` | `None` | `None` | **False** | `IntegrityError` propagates unchanged (**not** 409) |

`SKU_CODE_UNIQUE_CONSTRAINTS == ("skus_sku_code_key", "ux_skus_sku_code")`
verified by assertion, and `skus_sku_code_key UNIQUE (sku_code)` confirmed live
in every tenant schema (`pg_constraint`); `ux_skus_sku_code` is the legacy
public-schema unique index created by alembic `004_phase_b4_sku_inventory_mvp.py:54`.

**F-2 — finding (not a defect): the primary metadata path is inert on this
stack.** With SQLAlchemy 2.0.45 + asyncpg 0.31 the raised object is SQLAlchemy's
asyncpg-adapter `IntegrityError`, whose only attributes are `pgcode` and
`sqlstate` — neither `exc.orig.constraint_name` nor `exc.diag.constraint_name`
is populated. Classification therefore resolves through the guard's last
resort, the quoted-name test
`any(f'"{c}"' in str(orig or "") for c in SKU_CODE_UNIQUE_CONSTRAINTS)`, which
matched `"skus_sku_code_key"` in the rendered driver message
(`… violates unique constraint "skus_sku_code_key" DETAIL: Key (sku_code)=(…) already exists.`).
Behaviour is correct and bounded — 23514 and 23502 both classified False and
propagated unchanged — but correctness rests on a string test rather than on
driver metadata, so the P2 claim "uses reliable PostgreSQL/driver metadata" is
only **partially** satisfied. Recommended hardening (not applied): also accept a
strict `sqlstate == '23505'` plus a regex-extracted `constraint "…"` name, and
fail closed when neither the driver name nor a parseable message is available.

---

## 6. Focused verification

Fresh PostgreSQL 16 databases, each built from empty through the real alembic
chain to head `038`; the natural-order and reverse-order runs used **separate**
databases.

| Run | Database | Order | Collection | Result | Accounting |
|---|---|---|---|---|---|
| New tests independently | `test_k1_focus_a` | natural | 13 | **13 passed / 0 failed** | 13+0+0 = 13, gap=0 |
| Focused SKU/B2/S3 set | `test_k1_focus_a` | natural | 174 | **172 passed / 0 failed / 2 skipped** | 172+0+2 = 174, gap=0 |
| Focused SKU/B2/S3 set | `test_k1_focus_b` | **reverse** | 174 | **172 passed / 0 failed / 2 skipped** | 172+0+2 = 174, gap=0 |

JUnit node sets of the natural and reverse runs are **identical** (174/174,
symmetric difference 0); the 13 new-test nodes are a subset of the focused set.

Focused set (`/home/ivy/Documents/Codex/kilo-r1-k1/focus-set.txt`):
`test_sku_r1_multipackaging_closure.py`, `test_sku_r1_client_catalog_contract.py`,
`test_sku_b2_catalog_serialization.py`, `test_sku_m1_api_rbac.py`,
`test_sku_m1_catalog_identity.py`, `test_sku_m1_migration_pg16.py`,
`test_dc12r1_s3_s1_catalog_order_hardening.py`,
`test_s5c_runtime_sku_import_http_integration.py`,
`test_u4ib2_intake_apply_service.py`, `test_u3b2_preview_validate.py`.

Additional gate: `python tests/sku_b2_serialization_mutations.py` →
**all mutations RED as intended, pristine/restore GREEN** (M03 and M06 are
source-guard probes reported GREEN by design).

**No failure occurred in any focused run, so no failure needed classification
and no run was repeated.**

---

## 7. Full backend authority — single launch

Profile: the registered **`AUTHORITY_SKU_M1_BACKEND`**
(`harness-governance/inventory/authority-profiles.json`; expected head
`038_catalog_identity_vertical_slice`, expected parent
`037_payment_declarations_schema`, 15 required traps, runner
`harness-governance/validator/authority_runner.py`).

Environment exported **before collection and before the launch**
(`/home/ivy/Documents/Codex/kilo-r1-k1/env-authority.sh`): `TEST_DATABASE_URL`,
`DATABASE_URL` (normal application URL, same value), `REDIS_URL`,
`PW1R3_TEST_REDIS_URL`, `MPANGO_ENV=test`, `REPORTING_USER_PASSWORD`,
`SECRET_KEY`, `J1H2C_RETAILER_EMAIL`, `MPANGO_ALLOW_TEMP_DB_CREATE=1`,
`MPANGO_TEMP_DB_ALLOWED_PORTS=18830`, `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`.
Chain base `--baseline-sha c5215df80c8ea5e698cddea0a6809167356629da` (ancestor,
≠ parent `a45fe99e`).

Runner invocation (cwd = candidate worktree root):

```
python harness-governance/validator/authority_runner.py \
  --profile harness-governance/inventory/authority-profiles.json \
  --profile-id AUTHORITY_SKU_M1_BACKEND \
  --node-manifest …/artifacts/k1-authority-node-manifest.txt \
  --collect-target backend/tests \
  --baseline-sha c5215df80c8ea5e698cddea0a6809167356629da \
  --proof-out …/artifacts/et1-collect-proof.json \
  --sessionstart-out …/artifacts/et1-sessionstart-proof.json \
  --publish-dir …/artifacts/authority \
  --authority --command <venv>/bin/python -m pytest -p no:cacheprovider \
      --junitxml=…/artifacts/junit-authority.xml -rfE tests
```

### 7.1 Manifest, child proof, JUnit

| Item | Value |
|---|---|
| State trace | `INIT→PREFLIGHT→COLLECT_PROVEN→AUTHORIZED→RUNNING→FINISHED` (ALLOWED_TRANSITIONS) |
| `expected_node_count` / `collected_node_count` | **3826 / 3826** |
| `manifest_transport_bound` / `_match` | **true / true** |
| `nonce_match`, `child_sha_match` (candidate/profile/manifest) | **true**, all three **true** |
| `redis_module_bound/_match`, `backend_env_bound`/`tempdb_match`, `alembic_expected_bound/_match` | **true / true**, **true / true**, **true / true** |
| Node-set identity | **manifest == child proof == JUnit — 3826/3826/3826, symmetric difference 0** (JUnit `classname`+`name` resolved to file-path node ids and disk-checked: 0 manifest nodes whose file is missing) |
| `sentinel_calls` | **1** |
| `collect_child_spawns` | **1** |
| `command_exit_code` | **0** |
| `RUN_VERDICT` | **AUTHORITY_EXECUTED_GREEN** |

### 7.2 Accounting

```
tests (JUnit) = 3826
  passed  = 3763
  failed  = 0
  errors  = 0
  skipped = 63   (skip = 48, xfail = 15, xpass = 0)
3763 + 0 + 0 + 48 + 15 = 3826 = collected  ->  gap = 0
```

### 7.3 Classification of non-green nodes

**None required.** `failures = 0` and `errors = 0`, so there is no
`TEST_INFRASTRUCTURE`, `STALE_TEST_CONTRACT`, `CURRENT_PRODUCT_DEFECT` or
`ENVIRONMENT_GATED` node in the authority run. The 48 skips and 15 xfails are
pre-registered, non-failing outcomes and were not re-labelled.

### 7.4 Honest disclosure — one aborted launch attempt

A first invocation of the *same* command was started at 06:26:41 and was
**terminated by the operator's own tooling watchdog at ~T+2 min** (the shell
tool's default 120 s limit), not by any trap, product failure or environment
condition. It produced no verdict, no publish artifact and no JUnit file
(verified: no `junit-authority.xml`, `artifacts/authority/` still held the
earlier discovery-run files). Before the completed launch the authority database
was **dropped and recreated** and the real alembic chain was re-applied from
empty to head `038`, and Redis DB15 was confirmed empty, restoring the required
fresh-database precondition. The completed launch is therefore the only launch
that produced a verdict; its runner reports `sentinel_calls=1` (per-process
counter) and `collect_child_spawns=1`. **No correction-and-rerun occurred**: no
product, test, migration, frontend or harness file was edited at any point, and
no node was skipped, xfailed, deselected or weakened.

### 7.5 F-3 — hygiene observation (not a defect)

`backend/.hypothesis/unicode_data/15.0.0/codec-utf-8.json.gz` is a **tracked**
hypothesis cache artifact that the test suite rewrites at runtime; it was already
modified by the candidate commit itself (it appears in the `a45fe99e..c2c3bff3`
changed-path set) and was modified again by running the suite. It should be
git-ignored/untracked. Also noted: `backend/tests/test_sku_r1_multipackaging_closure.py:40-45`
carries a `setdefault` fallback with hard-coded test credentials
(`r1_auth:r1auth-…@127.0.0.1:17751/test_r1_multipack_backend`). The suite's
conftest overwrites `DATABASE_URL`, so the fallback never applies in this
environment, but hard-coded credential strings in a test file are poor hygiene.
Neither item is a product defect.

---

## 8. Proof that ZCODE author artifacts were not reused as authority

* Separate git worktree (`candidate-c2c3bff3`, detached at the exact candidate)
  and a second worktree for the report branch; neither was shared with any prior
  task directory.
* New Docker network (`kilo_r1_k1_net`) and containers
  (`kilo_r1_k1_pg16`, `kilo_r1_k1_redis7`) on previously unused ports
  18830 / 18831; four new databases created empty and migrated here.
* New venv `.venv-k1`, built here from `backend/requirements.txt`.
* All manifests, proofs, JUnit files and logs were produced by this run into
  `/home/ivy/Documents/Codex/kilo-r1-k1/artifacts/`.
* The ZCODE author report was only inspected through `git diff --name-status` /
  `--numstat` (to prove it is report-only); its content was never read and none
  of its evidence was used.
* `LUBUNTU_BROWSER_AUTHORITY_NOT_RUN`: no Playwright/browser execution and no
  H2-C evaluation took place in this task.

---

## 9. Required explicit statements

```
H2-C_NOT_EVALUATED
ZCODE_AUTHOR_EVIDENCE_NOT_REUSED_AS_AUTHORITY
KILO_PRODUCT_REVIEW_INDEPENDENT
BACKEND_AUTHORITY_SINGLE_LAUNCH
LUBUNTU_BROWSER_AUTHORITY_NOT_RUN
PRICING_NOT_STARTED
ORDER_PRICE_NOT_STARTED
REORDER_NOT_STARTED
```

---

## 10. Cleanup evidence

Destroyed after the branch push (task-owned only; host-owner containers such as
`mpango_postgres`, `mpango_redis`, `sku_m1_a5_*` were left untouched):

* containers `kilo_r1_k1_pg16`, `kilo_r1_k1_redis7` (removed, with their volumes)
* network `kilo_r1_k1_net` (removed)
* databases `test_k1_probe`, `test_k1_focus_a`, `test_k1_focus_b`,
  `test_k1_authority` and role `k1_auth` (dropped with the container)
* worktrees `candidate-c2c3bff3` (pruned) and `report-c2c3bff3` (kept only until
  push, then pruned)
* venv `.venv-k1`, `frontend/node_modules`, all `/tmp/opencode/k1-*` scratch
  files, and the probe scripts under `/home/ivy/Documents/Codex/kilo-r1-k1/probes/`

Only the report branch was pushed:
`reports/dc12r1-mvp-l1-sku-r0-m1-r1-r1-k1-kilo-backend-authority-2026-09-01`.
`source`, `product-dev-recovered`, `platform-dev` and `main` were **not** pushed.
