# U3-A: Product Data Ingress Discovery & Design

**Branch:** `codebuddy/u3a-product-data-ingress-discovery-2026-06-11`
**Date:** 2026-06-11
**Sprint:** U3-A (Research & Design — No Production Code Changes)
**Author:** AI Engineer
**Status:** Pending CTO Review

---

## 1. Current State

### 1.1 SKU Data Model

The `skus` table (created in Alembic migration `004_phase_b4_sku_inventory_mvp.py`) lives inside each tenant schema (`t_dev`, `t_test`, etc.) and has exactly **6 business fields**:

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | Inherited from `BaseModel` |
| `sku_code` | VARCHAR(64) | UNIQUE, NOT NULL | Human-readable product code |
| `name` | VARCHAR(255) | NOT NULL | Product display name |
| `description` | TEXT | nullable | Free-text description |
| `unit` | VARCHAR(32) | nullable | e.g. "kg", "pack", "box" |
| `category` | VARCHAR(64) | nullable | e.g. "Flour", "Beverages" |
| `is_active` | BOOLEAN | default `true` | Soft toggle |
| `created_at`, `updated_at` | TIMESTAMP | auto | From `AuditMixin` |
| `is_deleted`, `deleted_at` | BOOLEAN / TIMESTAMP | soft-delete | From `AuditMixin` |
| `created_by`, `updated_by` | UUID | nullable | From `UserTrackingMixin` |

**What is missing:** No `barcode`, no `image_url`, no `price` (pricing is separate), no `custom_attributes`, no `tags`, no `brand`, no `weight/volume` fields.

### 1.2 Related Data Tables

| Table | Relationship | Key Detail |
|-------|-------------|------------|
| `inventory_stocks` | 1:1 per SKU | Auto-created via `ensure_stock_row()` — `quantity_on_hand`, `quantity_reserved` |
| `inventory_movements` | Many per SKU | Audit journal of all stock changes |
| `retailer_prices` | Many per SKU | `retailer_id + sku_id → price` (UNIQUE constraint on pair) |
| `order_items` | Many per SKU | References `sku_code` + `product_name` (denormalized) |

### 1.3 Current SKU Creation Flow

```
User fills SKUFormModal → POST /api/v1/skus → SKUService.create_sku()
  → checks duplicate sku_code → SKURepository.create() → DB INSERT
  → inventory_ensure_stock_row() creates matching inventory_stocks row
```

- **Single-record only**: No bulk/batch API endpoints exist.
- **Frontend form**: `SKUFormModal.tsx` with fields: `sku_code`, `name`, `description`, `unit`, `category` — mirrors DB columns exactly.
- **Service validation**: Checks for duplicate `sku_code` within tenant schema before insert.

### 1.4 Existing Data Volume

The seed script (`backend/scripts/seed_demo_data.py`) creates **10 demo SKUs** — all Kenyan FMCG products (maize flour, sugar, cooking oil, rice, tea, soap, salt). This reflects the current target market: East African wholesale/distribution businesses with product catalogs ranging from 20 to 500+ SKUs.

### 1.5 JSONB Extensibility Precedents

The codebase already uses JSONB columns in two places:

1. **`sys_audit_logs.metadata_`** (JSONB) — stores arbitrary key-value audit metadata
2. **`platform_tenants.provisioning_log`** (JSONB) — stores tenant provisioning events

This establishes JSONB as an accepted extensibility pattern in the project, though it has not been applied to the SKU/product domain.

### 1.6 Multi-Tenant Architecture

- **Schema-per-tenant**: Each tenant gets its own PostgreSQL schema (`t_dev`, `t_test`, etc.)
- **Global tenant filter**: SQLAlchemy `do_orm_execute` event + `ContextVar`-based tenant context automatically scopes all queries
- **Bootstrap DDL**: `bootstrap_tenant_schema.py` creates all tables (including `skus`) per tenant schema
- **Implication**: Any schema change to `skus` must be applied via Alembic migration across all tenant schemas

---

## 2. Problem Statement

### 2.1 The Core Problem

A new tenant signing up for Mpango typically has an existing product catalog — often in a spreadsheet (Excel/CSV), sometimes in another system (QuickBooks, Tally, WhatsApp catalog). Today, they must enter every product **one at a time** through the SKU form modal. For a business with 200 SKUs, this is a 2-4 hour tedious task that creates immediate friction at onboarding.

### 2.2 Specific Pain Points

1. **No bulk creation**: Every product must be entered individually via a modal form
2. **No field mapping**: Tenants coming from different systems have different column names and structures
3. **No custom attributes**: A flour distributor needs "grade" (e.g., "Grade 1", "Grade 2"); a beverage distributor needs "volume" (e.g., "500ml", "1L"). The current rigid schema supports none of this.
4. **No barcode/EAN support**: Many FMCG distributors track products by barcode, which Mpango cannot capture or scan
5. **No image support**: Product images help field sales teams identify items quickly — currently not possible
6. **No import validation feedback**: When bulk data has errors (duplicates, missing fields), there is no mechanism to report row-level errors
7. **No permission gating**: There is no role-based gate for "who can import products" vs "who can view products"

### 2.3 Design Constraints

- **Do not break existing single-SKU creation flow** — it must continue working
- **Schema-per-tenant architecture** — any DDL change propagates to all tenant schemas
- **Mobile-first users** — many Mpango users are on phones, so field mapping UX must be simple
- **East African market** — CSV is more common than Excel; mobile scanning (camera) is high-value future

---

## 3. Design Options

### 3.1 Option A: Rigid CSV Import (Simplest)

**Approach:** Define a fixed CSV template with columns matching `skus` table exactly: `sku_code`, `name`, `description`, `unit`, `category`. Users must format their data to match.

**Pros:**
- Simplest to implement (~2 days)
- No schema changes needed
- Predictable validation rules

**Cons:**
- Cannot handle custom attributes
- Users must reformat their data to match Mpango's template — friction
- No extensibility path; any new field requires template change + migration
- **CTO directive explicitly warns against this**: "不把 CSV-only 作为最终架构"

**Verdict: Not recommended as final architecture. Could be a tactical v1 shortcut, but locks us into rigidity.**

---

### 3.2 Option B: Flexible Field Mapping + Custom Attributes (JSONB)

**Approach:**
1. User uploads CSV/Excel with **any column structure**
2. Mpango shows a **field mapping UI**: "Which of your columns maps to Product Code? Product Name? Category?"
3. Unmapped columns are optionally stored in a new `custom_attributes` JSONB column on `skus`
4. Backend provides a **batch SKU creation endpoint** (`POST /api/v1/skus/batch`)

**Schema change:**
```sql
ALTER TABLE skus ADD COLUMN custom_attributes JSONB DEFAULT '{}';
```

**Pros:**
- Accepts any CSV format — users don't reformat their data, they map it
- Custom attributes via JSONB support tenant-specific needs without schema changes
- JSONB is already an accepted pattern in the codebase
- Extensible to barcode, brand, weight, etc. without migrations
- Field mapping UI is reusable for future import types (customers, orders)

**Cons:**
- More complex frontend (mapping wizard: 2-3 extra screens)
- JSONB queries are slower than native columns for filtering/sorting
- Need to decide: which attributes are "native" (searchable/sortable) vs "custom" (display-only)
- Batch endpoint needs careful transaction management (partial success handling)

**Estimated effort:** 4-6 days (backend 2 days + frontend field mapping 3 days + testing 1 day)

---

### 3.3 Option C: EAV (Entity-Attribute-Value) for Custom Fields

**Approach:** Create a `sku_attributes` table with `sku_id`, `attribute_name`, `attribute_value` columns.

**Pros:**
- Fully normalized — each custom attribute is a queryable row
- Supports typed values (string, number, date)

**Cons:**
- Complex queries (self-joins per attribute)
- Poor performance at scale
- Overkill for current Mpango scale (50-500 SKUs per tenant)
- No existing precedent in the codebase

**Verdict: Over-engineered for current scale. JSONB is simpler and already proven in the codebase.**

---

### 3.4 Option D: Full Product Information Management (PIM) System

**Approach:** Build a complete PIM with product families, variants, multi-channel publishing, etc.

**Verdict: Far beyond current MVP scope. Defer to long-term roadmap.**

---

### Recommendation Summary

| Option | Flexibility | Complexity | Extensibility | Fit |
|--------|------------|------------|---------------|-----|
| A: Rigid CSV | Low | Low | None | Poor |
| **B: Field Mapping + JSONB** | **High** | **Medium** | **High** | **Best** |
| C: EAV | High | High | High | Over-engineered |
| D: Full PIM | Very High | Very High | Very High | Future |

**Recommended: Option B** — Field mapping + JSONB custom attributes. Balances flexibility, implementation cost, and extensibility.

---

## 4. Recommended MVP Slice (U3-B Scope)

### 4.1 MVP Scope: "Upload & Map"

The MVP implements the minimum viable version of Option B:

#### Backend Changes

| Component | Change | Files |
|-----------|--------|-------|
| **SKU Model** | Add `custom_attributes JSONB DEFAULT '{}'` | `backend/models/sku.py` |
| **Alembic Migration** | New migration adding `custom_attributes` column | `backend/alembic/versions/0xx_sku_custom_attributes.py` |
| **Pydantic Schemas** | Add `custom_attributes: Optional[Dict[str, Any]]` to Create/Update/Read | `backend/schemas/sku.py` |
| **Batch Endpoint** | `POST /api/v1/skus/batch` — accepts array of SKU dicts + field mapping spec | `backend/api/v1/skus.py` |
| **Batch Service** | `SKUService.create_skus_batch()` — validates, deduplicates, inserts within transaction | `backend/services/sku_service.py` |
| **Import Endpoint** | `POST /api/v1/skus/import` — accepts CSV file upload, returns parsed columns + preview | `backend/api/v1/skus.py` |
| **Import Service** | `ImportService.parse_csv()` — CSV parsing with encoding detection | New: `backend/services/import_service.py` |

**Batch endpoint behavior:**
```python
# Request
POST /api/v1/skus/batch
{
  "skus": [
    {"sku_code": "F001", "name": "Maize Flour 2kg", "category": "Flour",
     "custom_attributes": {"brand": "Jogoo", "grade": "Grade 1"}},
    ...
  ],
  "on_conflict": "skip"  # or "update" or "error"
}

# Response
{
  "created": 45,
  "skipped": 3,
  "updated": 0,
  "errors": [
    {"row": 12, "sku_code": "F001", "error": "duplicate sku_code"}
  ]
}
```

#### Frontend Changes

| Component | Change | Files |
|-----------|--------|-------|
| **Import Wizard Step 1** | Upload CSV/Excel file, show raw preview | New: `frontend/src/pages/skus/ImportWizard/` |
| **Import Wizard Step 2** | Field mapping UI: drag/map CSV columns → Mpango fields + custom attributes | New: `frontend/src/pages/skus/ImportWizard/Step2FieldMapping.tsx` |
| **Import Wizard Step 3** | Preview mapped data, show validation errors, confirm import | New: `frontend/src/pages/skus/ImportWizard/Step3Preview.tsx` |
| **SKU Form Update** | Add `custom_attributes` display/edit section | `frontend/src/pages/skus/SKUFormModal.tsx` |
| **SKU List Update** | Show custom attribute columns (configurable) | `frontend/src/pages/skus/SKUListPage.tsx` |
| **Import Service** | Frontend service wrapping import/batch API calls | New: `frontend/src/services/importService.ts` |

**Import wizard UX flow:**
```
Step 1: Upload File
  → Drag & drop or click to upload .csv/.xlsx
  → Backend parses, returns: {columns: [...], rows_preview: [...], row_count: N}

Step 2: Map Fields
  → Left: CSV columns. Right: Mpango fields (sku_code*, name*, description, unit, category)
  → "Add custom attribute" button for unmapped columns
  → Required fields highlighted (sku_code, name)
  → Save mapping as template for future use (optional, post-MVP)

Step 3: Preview & Import
  → Show first 10 rows with mapped data
  → Highlight validation errors (missing required, duplicate sku_codes)
  → "Import N products" button
  → Progress bar during import
  → Results summary: "Created 45, Skipped 3, Errors 2"
```

### 4.2 Explicitly Out of Scope for MVP

| Feature | Reason |
|---------|--------|
| Image upload/import | Requires file storage infrastructure (S3/CloudBase Storage) — defer to U3-C |
| Barcode scanning | Requires camera API integration — defer to U4 |
| Excel (.xlsx) support | Start with CSV only; add xlsx parsing after core flow works |
| Import templates (save/load mappings) | Nice-to-have, defer |
| Role-based import permissions | Current auth model doesn't have roles yet — defer |
| Webhook/API-based product sync | Requires external API design — long-term roadmap |
| Product variants (size, flavor) | Requires variant data model design — separate discovery |

### 4.3 Estimated Effort

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Backend: migration + batch endpoint | 1 day | Working `POST /skus/batch` + `POST /skus/import` |
| Backend: CSV parsing + validation | 0.5 day | Import service with row-level error reporting |
| Frontend: Import wizard (3 steps) | 2 days | Complete upload → map → preview flow |
| Frontend: SKU form custom attributes | 0.5 day | Editable key-value section in SKU form |
| Testing & polish | 1 day | Edge cases, encoding issues, large files |
| **Total** | **5 days** | |

---

## 5. Future Roadmap

### Phase 1 (U3-B): CSV Import with Field Mapping — 5 days
As described in Section 4. Core bulk import capability.

### Phase 2 (U3-C): Product Images — 3 days
- Add `image_url` column to `skus` (VARCHAR, nullable)
- Integrate with CloudBase Storage or S3 for image hosting
- Support image upload in SKU form and bulk import (ZIP file with images, filename → sku_code mapping)
- Thumbnail generation for SKU list view

### Phase 3 (U4-A): Barcode Support — 3 days
- Add `barcode` column to `skus` (VARCHAR, nullable, indexed)
- Mobile camera scan: integrate browser BarcodeDetector API or QuaggaJS
- Barcode search in SKU list and order creation
- Support EAN-13, Code-128 formats

### Phase 4 (U5-A): Excel Support & Import Templates — 2 days
- Add xlsx parsing (using `openpyxl` backend / SheetJS frontend)
- Save/load field mapping templates per tenant
- Auto-detect common formats (first row = headers detection improvement)

### Phase 5 (U6-A): Custom Attribute Schema — 5 days
- Move from ad-hoc JSONB to a managed custom attribute system:
  - `sku_attribute_definitions` table: tenant defines attribute name, type (text/number/select), options
  - `sku_attributes` remains JSONB but is validated against definitions
  - Admin UI to manage attribute definitions
- Enables typed filtering, faceted search, dropdown options

### Phase 6 (Long-term): External Integrations — 10+ days
- QuickBooks product sync
- Tally ERP integration
- WhatsApp Business Catalog import
- REST API for third-party product data push

---

## 6. Risks and Open Questions

### 6.1 Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **CSV encoding issues** (UTF-8 vs Latin-1, BOM headers) | Medium | Use `chardet` for encoding detection; strip BOM on parse |
| **Large file imports** (>1000 rows) blocking | Medium | Batch inserts in chunks of 100; async progress reporting via polling or WebSocket |
| **JSONB query performance** at scale | Low | Current scale (50-500 SKUs/tenant) is trivial for JSONB. Add GIN index if needed later |
| **Field mapping UX complexity** on mobile | Medium | Design mobile-first mapping wizard; use dropdowns instead of drag-and-drop |
| **Migration rollback** if custom_attributes causes issues | Low | JSONB column is nullable with default — safe to add, safe to ignore |
| **Duplicate sku_code handling** in batch | Medium | Support `on_conflict: skip | update | error` strategies — let tenant choose |
| **Data quality** from messy spreadsheets | High | Provide clear validation feedback with row numbers; require manual fix before import |

### 6.2 Open Questions for CTO

1. **Custom attributes scope**: Should custom attributes be searchable/filterable in the product list, or display-only initially? (Recommendation: display-only for MVP, searchable in Phase 5)

2. **Conflict strategy default**: When importing SKUs that already exist, should the default be `skip` or `error`? (Recommendation: `skip` with clear count in results)

3. **Tenant attribute sharing**: Should attribute definitions be shareable across tenants (e.g., a "standard FMCG attribute pack"), or purely per-tenant? (Recommendation: per-tenant for MVP)

4. **Import permission**: Should there be a permission gate on import? Currently all authenticated users in a tenant can create SKUs. (Recommendation: no change for MVP, add when role system exists)

5. **File size limit**: Maximum CSV file size for import? (Recommendation: 5MB / 5000 rows for MVP — covers 95% of target users)

6. **Category standardization**: Should categories be free-text or from a predefined list? Currently free-text. Import would benefit from a category picker or auto-suggest. (Recommendation: keep free-text for MVP, add category management in Phase 5)

7. **Inventory initial quantity**: When importing SKUs, should users also be able to set initial stock quantities in the same import? The `inventory_stocks` row is auto-created at 0. (Recommendation: defer to separate "stock adjustment import" feature — keep SKU import focused on product data)

---

## 7. Exact Files Read

### Backend — Models
| File | Purpose |
|------|---------|
| `backend/models/sku.py` | SKU ORM model — 6 business fields, no extensibility |
| `backend/models/base.py` | BaseModel, AuditMixin, UserTrackingMixin inheritance chain |
| `backend/models/inventory_stock.py` | InventoryStock — 1:1 per SKU, auto-created |
| `backend/models/inventory_movement.py` | InventoryMovement — stock audit journal |
| `backend/models/retailer_price.py` | RetailerPrice — pricing is separate from SKU |
| `backend/models/order.py` | Order + OrderItem — denormalized sku_code reference |
| `backend/models/audit.py` | SysAuditLog — JSONB `metadata_` precedent |
| `backend/models/platform_tenant.py` | PlatformTenant — JSONB `provisioning_log` precedent |

### Backend — API / Services / Repositories
| File | Purpose |
|------|---------|
| `backend/api/v1/skus.py` | SKU CRUD routes — single-record only |
| `backend/services/sku_service.py` | SKUService — create_sku with duplicate check |
| `backend/repositories/sku_repository.py` | SKURepository — basic CRUD operations |
| `backend/schemas/sku.py` | Pydantic schemas — mirrors DB columns exactly |
| `backend/api/v1/inventory.py` | Inventory routes — shows stock lifecycle |
| `backend/services/inventory_service.py` | InventoryService — SELECT FOR UPDATE pattern |
| `backend/api/v1/pricing.py` | Pricing routes — retailer+SKU pricing |
| `backend/core/domain/order_state.py` | Order state machine — references sku_code |

### Backend — Infrastructure
| File | Purpose |
|------|---------|
| `backend/db/tenant_filter.py` | Schema-per-tenant filtering via SQLAlchemy event |
| `backend/scripts/seed_demo_data.py` | Demo seeder — 10 Kenyan FMCG products |
| `backend/scripts/bootstrap_tenant_schema.py` | Tenant bootstrap DDL — all table CREATE statements |
| `backend/alembic/versions/004_phase_b4_sku_inventory_mvp.py` | Migration creating `skus` + `inventory_stocks` |
| `backend/alembic/versions/017_retailer_prices.py` | Migration creating `retailer_prices` |

### Frontend
| File | Purpose |
|------|---------|
| `frontend/src/services/skuService.ts` | SKU API service — getAll, create, update |
| `frontend/src/pages/skus/SKUFormModal.tsx` | SKU creation/edit form — 5 fields |
| `frontend/src/pages/skus/SKUListPage.tsx` | SKU list with empty state + import placeholder |
| `frontend/src/types/inventory.ts` | StockView type |
| `frontend/src/types/pricing.ts` | RetailerPriceView type |
| `frontend/src/types/order.ts` | Order types |
| `frontend/src/types/client.ts` | Client-facing product types |
| `frontend/src/services/clientProductService.ts` | Retailer-facing product service |

---

## 8. Proposed U3-B Implementation Plan

### 8.1 Branch Strategy

```
Branch: codebuddy/u3b-product-csv-import-2026-06-12
Base:   origin/product-dev-recovered
```

### 8.2 Implementation Order

#### Day 1: Backend Foundation
1. Create Alembic migration adding `custom_attributes JSONB DEFAULT '{}'` to `skus`
2. Update `SKU` model, Pydantic schemas to include `custom_attributes`
3. Implement `POST /api/v1/skus/batch` endpoint with:
   - Array input validation
   - Duplicate `sku_code` detection within batch + against existing
   - `on_conflict` strategy (skip / update / error)
   - Row-level error reporting
4. Implement `POST /api/v1/skus/import` endpoint:
   - Accept `multipart/form-data` CSV file upload
   - Parse CSV with `chardet` encoding detection
   - Return `{columns, rows_preview, row_count}`
5. Unit tests for batch endpoint edge cases

#### Day 2-3: Frontend Import Wizard
6. Create `ImportWizard` component structure:
   - `Step1Upload.tsx` — file drop zone, calls `/skus/import`
   - `Step2FieldMapping.tsx` — map CSV columns to Mpango fields
   - `Step3Preview.tsx` — show mapped data preview, validation errors, confirm button
7. Create `importService.ts` — API wrapper for import/batch endpoints
8. Wire up ImportWizard from SKUListPage "Import Products" button
9. Handle results display: success count, skip count, error details

#### Day 4: SKU Form + Polish
10. Update `SKUFormModal.tsx` — add custom attributes key-value editor
11. Update `SKUListPage.tsx` — show custom attributes in table (optional columns)
12. Update `skuService.ts` — support `custom_attributes` in create/update

#### Day 5: Testing & Edge Cases
13. Test with messy CSV files (BOM, mixed encodings, missing fields, extra columns)
14. Test batch sizes: 10, 100, 500, 1000 rows
15. Test error scenarios: all-duplicate, partial-failure, empty file
16. Update ledger, run lint/build/check, push

### 8.3 Validation Commands

```bash
pnpm lint                          # 0 errors
pnpm build                         # pass
git diff --check origin/product-dev-recovered..HEAD  # no whitespace issues
```

### 8.4 Definition of Done

- [ ] Tenant can upload a CSV file with any column structure
- [ ] Field mapping wizard correctly maps CSV columns to Mpango fields
- [ ] Unmapped columns are stored as custom attributes
- [ ] Batch import creates SKUs with row-level error reporting
- [ ] Existing single-SKU creation flow still works unchanged
- [ ] Import results show created/skipped/errored counts
- [ ] No production code changes outside the U3-B scope

---

## Appendix A: CSV Import Flow Diagram

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐     ┌──────────────┐
│  Upload CSV  │────▶│  Parse &     │────▶│  Field Mapping │────▶│  Preview &   │
│  File        │     │  Detect Cols │     │  (user maps    │     │  Validate    │
└─────────────┘     └──────────────┘     │  columns)      │     └──────┬───────┘
                                         └────────────────┘            │
                                                                       ▼
                                                              ┌──────────────┐
                                                              │  POST        │
                                                              │  /skus/batch │
                                                              └──────┬───────┘
                                                                     │
                                                         ┌───────────┴──────────┐
                                                         ▼                      ▼
                                                  ┌─────────────┐     ┌──────────────┐
                                                  │  Success:   │     │  Errors:     │
                                                  │  N created  │     │  Row-level   │
                                                  │  M skipped  │     │  details     │
                                                  └─────────────┘     └──────────────┘
```

## Appendix B: Field Mapping UI Wireframe

```
┌─────────────────────────────────────────────────────┐
│  Map Your Columns to Mpango Products                │
│─────────────────────────────────────────────────────│
│                                                     │
│  Your CSV Columns          Mpango Fields            │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Product Code │─────────▶│ sku_code *       │     │
│  └──────────────┘          └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Product Name │─────────▶│ name *           │     │
│  └──────────────┘          └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Category     │─────────▶│ category         │     │
│  └──────────────┘          └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Unit Type    │─────────▶│ unit             │     │
│  └──────────────┘          └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Brand        │─────────▶│ + Custom Attr    │     │
│  └──────────────┘          │  "brand"         │     │
│                            └──────────────────┘     │
│  ┌──────────────┐          ┌──────────────────┐     │
│  │ Weight       │─────────▶│ + Custom Attr    │     │
│  └──────────────┘          │  "weight"        │     │
│                            └──────────────────┘     │
│                                                     │
│  * Required fields                                  │
│                                                     │
│  [  Back  ]                          [ Next: Preview ]│
└─────────────────────────────────────────────────────┘
```

---

**End of U3-A Discovery Report — Awaiting CTO Review**
