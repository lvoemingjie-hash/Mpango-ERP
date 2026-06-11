# U3-A: Product Data Ingress Discovery & Design (R2 Revised)

**Branch:** `codebuddy/u3a-product-data-ingress-discovery-2026-06-11`
**Date:** 2026-06-11
**Sprint:** U3-A (Research & Design — No Production Code Changes)
**Revision:** R2 (2026-06-11 23:28) — Agent-operable 3-phase import contract, U3-B re-ordered to 5 backend-first slices
**Author:** AI Engineer
**Status:** Pending CTO Final Approval

**CTO Direction Confirmed:** U3 first builds the agent-operable data ingress kernel (preview→validate→apply contract), then wraps it in the human-friendly import wizard UI.

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

### 1.7 Existing RBAC Permission System

**This is critical context that the original U3-A report missed.** Mpango already has a full Role-Based Access Control system. The claim in Section 2.2.7 ("No permission gating") was incorrect.

#### Permission Model

| Table | Location | Purpose |
|-------|----------|---------|
| `permissions` | Tenant schema | Permission codes: `skus:read`, `skus:create`, `skus:update`, `orders:create`, etc. |
| `roles` | Tenant schema | Roles: `admin`, `sales`, `warehouse`, `finance` |
| `role_permissions` | Tenant schema | M2M join: which roles hold which permissions |
| `user_roles` | Tenant schema | M2M join: which users hold which roles |

The `Permission` model (`backend/models/user.py` lines 101-134) uses the format `<resource>:<action>` (e.g., `skus:create`). The `admin` role gets ALL permissions assigned at bootstrap.

#### Enforcement Mechanism

All SKU API routes already enforce permissions via `RequirePermission()` from `backend/api/middleware/rbac.py`:

```python
# backend/api/v1/skus.py (existing code)
@router.get("/")
async def list_skus(..., token = Depends(RequirePermission("skus:read"))): ...

@router.post("/")
async def create_sku(..., token = Depends(RequirePermission("skus:create"))): ...

@router.put("/{sku_code}")
async def update_sku(..., token = Depends(RequirePermission("skus:update"))): ...
```

`RequirePermission` checks the user's roles (loaded from DB via tenant context), collects all permission codes, and returns 403 if the required code is absent. Super admins bypass the check.

#### Current SKU-Related Permission Codes

| Code | Used By | Status |
|------|---------|--------|
| `skus:read` | `GET /skus`, `GET /skus/{code}` | Enforced |
| `skus:create` | `POST /skus` | Enforced |
| `skus:update` | `PUT /skus/{code}` | Enforced |
| **`skus:import`** | **Not yet defined** | **Missing — must be created in U3-B** |

#### Implication for U3-B

U3-B MUST:
1. Create a new `skus:import` permission code in the tenant schema
2. Register it in `create_wholesaler.py` + `seed_demo_data.py` (both seed the full permission list)
3. Protect `POST /skus/batch` and `POST /skus/import` with `RequirePermission("skus:import")`
4. Assign `skus:import` to the `admin` role at bootstrap
5. Decide whether to also assign it to `warehouse` role (warehouse staff often do bulk data entry)

**Do NOT rely on reusing `skus:create`**: Import is a fundamentally different operation — it is bulk, accepts raw file uploads, and has different error semantics. A separate permission allows tenants to grant "create one product at a time" without granting "import 500 products at once."

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
7. **Missing `skus:import` permission**: The existing RBAC system already gates `skus:read`, `skus:create`, `skus:update` (see Section 1.7). However, there is no `skus:import` permission code. The batch import endpoints would either need a new dedicated permission or a decision to reuse `skus:create`. **CTO directive: import requires its own permission — do not skip this.**

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

## 4. Agent-Operable / CLI-Friendly Import Contract (Architecture Constraint)

### 4.1 Why This Matters for AI-Native Mpango

Mpango is not just a human-operated ERP. It is being built as an **AI-native platform** where agents, CLI tools, and automated workflows can perform business operations with the same safety guarantees as human users. The product import capability must serve **two equally important audiences**:

| Audience | Entry Point | Needs |
|----------|------------|-------|
| **Human user** | Frontend Import Wizard (3-step UI) | Visual field mapping, drag-and-drop, progress bar |
| **AI agent / CLI / script** | REST API → `mpango` CLI | Structured JSON responses, idempotent steps, auditable decisions |

**Key principle:** The frontend Wizard is a consumer of the API contract, not the definition of it. The API contract must be designed for programmatic callers first, with the Wizard layered on top.

**Why this matters for AI agents specifically:**
1. AI should not guess database state — it must call tools that return structured results
2. High-risk writes must pass through system validation before any data is committed
3. An agent calling `apply` must be able to point to an audit record proving what happened
4. The same contract can be driven by `mpango products import --preview/--validate/--apply` CLI commands
5. Future AI assistants (CodeBuddy, Copilot, custom agents) can safely onboard tenant product catalogs without touching the UI

### 4.2 The Three-Phase Import Contract

Every product import — whether initiated by a human wizard, a CLI command, or an AI agent — MUST follow this contract:

```
Phase 1: PREVIEW   →  Phase 2: VALIDATE  →  Phase 3: APPLY
(no writes)            (no writes)           (writes + audit)
```

#### Phase 1: `preview`

**Purpose:** Parse the input, detect structure, return a stable `import_id` for subsequent phases. **No business table writes.**

| Input | Output |
|-------|--------|
| `POST /api/v1/skus/import/preview` | `{import_id, columns, sample_rows, row_count, detected_encoding}` |
| Body: CSV file (`multipart/form-data`) OR JSON rows + mapping | |

```json
// Response
{
  "import_id": "imp_a1b2c3d4",
  "source": {"filename": "products.csv", "encoding": "utf-8", "row_count": 150},
  "columns_detected": ["Product Code", "Product Name", "Category", "Unit", "Brand", "Weight"],
  "sample_rows": [
    {"Product Code": "F001", "Product Name": "Maize Flour 2kg", "Category": "Flour", "Unit": "bag", "Brand": "Jogoo", "Weight": "2kg"},
    {"Product Code": "F002", "Product Name": "Wheat Flour 1kg", "Category": "Flour", "Unit": "pack", "Brand": "Pembe", "Weight": "1kg"}
  ]
}
```

**Design rules:**
- The `import_id` is a system-generated UUID, opaque to the caller
- The import run record is stored in a new table (see Section 4.3) with status `previewed`
- Preview results are cached by `import_id` for subsequent phases
- Re-uploading generates a NEW `import_id` — previews are immutable snapshots

#### Phase 2: `validate`

**Purpose:** Apply field mapping and run all validation rules. Return structured row-level errors and warnings. **No business table writes.**

| Input | Output |
|-------|--------|
| `POST /api/v1/skus/import/{import_id}/validate` | `{import_id, valid_rows, error_rows, warning_rows, errors: [...], warnings: [...]}` |
| Body: field mapping JSON | |

```json
// Request
{
  "mapping": {
    "Product Code": "sku_code",
    "Product Name": "name",
    "Category": "category",
    "Unit": "unit",
    "Brand": "custom_attributes.brand",
    "Weight": "custom_attributes.weight"
  }
}

// Response
{
  "import_id": "imp_a1b2c3d4",
  "status": "needs_review",
  "valid_rows": 143,
  "error_rows": 7,
  "warning_rows": 12,
  "errors": [
    {"row": 5, "field": "sku_code", "message": "Missing required field"},
    {"row": 12, "field": "sku_code", "message": "Duplicate: F001 already exists in preview row 1"},
    {"row": 23, "field": "sku_code", "message": "F001 already exists in tenant database"},
    {"row": 45, "field": "name", "message": "Product name exceeds 255 characters"}
  ],
  "warnings": [
    {"row": 12, "field": "unit", "message": "Unknown unit: 'carton' (will be stored as-is)"},
    {"row": 67, "field": "category", "message": "New category: 'Beverages' (will be created)"}
  ]
}
```

**Validation rules (minimum):**
- Required fields present (`sku_code`, `name`)
- Duplicate `sku_code` within the import batch
- Duplicate `sku_code` against existing tenant products
- String length limits (`sku_code` ≤ 64, `name` ≤ 255, `unit` ≤ 32, `category` ≤ 64)
- Custom attribute keys are valid JSON keys (no dots, no spaces — or explicitly allowed)
- No SQL injection or XSS via field values

**Design rules:**
- Validation is idempotent — calling it twice with the same `import_id` + mapping returns the same result
- Mapping can be re-submitted to fix errors — each call re-validates
- Import run status updates to `validated` (with error counts)
- Caller decides whether to proceed with apply despite warnings

#### Phase 3: `apply`

**Purpose:** Execute the import. Write SKUs, custom attributes, and inventory stock rows. Create audit records. **Protected by `skus:import` permission.**

| Input | Output |
|-------|--------|
| `POST /api/v1/skus/import/{import_id}/apply` | `{import_id, created, skipped, updated, errors, audit_run_id}` |
| Body: `{on_conflict: "skip" | "update" | "error"}` | |

```json
// Response
{
  "import_id": "imp_a1b2c3d4",
  "status": "completed",
  "created": 140,
  "skipped": 3,
  "updated": 0,
  "errors": [
    {"row": 5, "sku_code": null, "error": "Missing sku_code — row was not imported"},
    {"row": 23, "sku_code": "F001", "error": "Already exists in tenant, skipped per on_conflict=skip"}
  ],
  "audit_run_id": "aud_run_x9y0z1",
  "applied_at": "2026-06-12T10:30:00Z",
  "applied_by": "user-uuid-here"
}
```

**Design rules:**
- Apply is **only callable on an import that has been validated** (status `validated` or `needs_review`)
- Apply is **not idempotent** — calling it twice on the same import with `on_conflict: skip` will skip all rows on the second call (already imported)
- Apply writes within a **database transaction** — partial success possible (some rows succeed, some fail)
- Every apply call creates an **audit record** (see Section 4.3)
- **Must be protected by `RequirePermission("skus:import")`** (same as preview/validate)
- The `applied_by` field captures the authenticated user UUID from the JWT

### 4.3 Import Run & Audit Record Model

To support the 3-phase contract and provide auditable import history, a new tenant-schema table is required:

```sql
CREATE TABLE import_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    import_id VARCHAR(64) NOT NULL UNIQUE,    -- matches the API import_id
    tenant_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'previewed',  -- previewed | validated | needs_review | applied | failed
    source_filename VARCHAR(255),
    source_encoding VARCHAR(32),
    total_rows INTEGER NOT NULL DEFAULT 0,
    valid_rows INTEGER,
    error_rows INTEGER,
    warning_rows INTEGER,
    mapping JSONB,                              -- the field mapping used
    validation_result JSONB,                    -- snapshot of validation output
    apply_result JSONB,                         -- snapshot of apply output
    created_rows INTEGER DEFAULT 0,
    skipped_rows INTEGER DEFAULT 0,
    updated_rows INTEGER DEFAULT 0,
    applied_by UUID REFERENCES users(id),
    applied_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

**Why this table exists:**
- Agents (and humans) need a stable reference to an import session across phases
- Audit requires knowing WHO imported WHAT, WHEN, and with WHAT RESULT
- The `validation_result` and `apply_result` JSONB columns capture full snapshots for post-mortem analysis
- This is **not** a replacement for `sys_audit_logs` — it is a business-level record of the import run. System-level audit (who called which endpoint) should also be written to `sys_audit_logs.metadata_` (using the existing JSONB audit precedent)

### 4.4 CLI Vision (Future)

The 3-phase contract enables a future `mpango` CLI:

```bash
# Step 1: Preview — what's in this file?
mpango products import --tenant TEST001 --file products.csv --preview
# → returns import_id, columns, sample_rows

# Step 2: Validate — does it pass our rules?
mpango products import --import-id imp_a1b2c3d4 --mapping mapping.json --validate
# → returns valid_rows, errors, warnings

# Iterate: fix errors, update mapping, re-validate
mpango products import --import-id imp_a1b2c3d4 --mapping mapping_v2.json --validate

# Step 3: Apply — go!
mpango products import --import-id imp_a1b2c3d4 --apply --on-conflict skip
# → returns created/skipped/errors + audit_run_id
```

This CLI does NOT need to be built in U3-B. It is a natural consumer of the API contract once the endpoints exist.

### 4.5 Contract Enforcement in U3-B

All three phases (`preview`, `validate`, `apply`) MUST:
1. Be accessible as REST endpoints under `/api/v1/skus/import/`
2. Be protected by `RequirePermission("skus:import")`
3. Return structured JSON responses as specified above
4. Carry the `import_id` through all phases
5. Log each phase transition to the `import_runs` table

The frontend Import Wizard (U3-B4) will call these same endpoints — it is a consumer, not a separate implementation path.

---

## 5. Recommended MVP Slice (U3-B Scope)

### 5.1 MVP Scope: "Upload & Map"

The MVP implements the minimum viable version of Option B:

#### Backend Changes

| Component | Change | Files |
|-----------|--------|-------|
| **SKU Model** | Add `custom_attributes JSONB DEFAULT '{}'` | `backend/models/sku.py` |
| **Alembic Migration** | New migration: `custom_attributes` on `skus` + new `import_runs` table | `backend/alembic/versions/0xx_sku_custom_attributes.py` |
| **Import Run Model** | ORM model for `import_runs` table (Section 4.3) | New: `backend/models/import_run.py` |
| **Pydantic Schemas** | Add `custom_attributes: Optional[Dict[str, Any]]` to Create/Update/Read; new `ImportPreview`, `ImportValidate`, `ImportApply` request/response schemas | `backend/schemas/sku.py`, New: `backend/schemas/import_schemas.py` |
| **Preview Endpoint** | `POST /api/v1/skus/import/preview` — CSV upload, returns `import_id` + columns + sample rows. **No writes.** | `backend/api/v1/skus.py` |
| **Validate Endpoint** | `POST /api/v1/skus/import/{import_id}/validate` — accepts mapping, returns row-level errors/warnings. **No writes.** | `backend/api/v1/skus.py` |
| **Apply Endpoint** | `POST /api/v1/skus/import/{import_id}/apply` — writes SKUs + custom_attributes + inventory + audit. **Writes + audit.** | `backend/api/v1/skus.py` |
| **Import Service** | `ImportService` with three public methods: `preview()`, `validate()`, `apply()`. `ImportService.parse_csv()` handles encoding detection. | New: `backend/services/import_service.py` |
| **Permission: skus:import** | New permission code + seed in `create_wholesaler.py` & `seed_demo_data.py`; assign to `admin` role. All three import endpoints protected by `RequirePermission("skus:import")`. | `backend/scripts/create_wholesaler.py`, `backend/scripts/seed_demo_data.py` |
| **Audit Logging** | Every `apply` call writes to `sys_audit_logs.metadata_` (using existing JSONB precedent) | `backend/services/import_service.py` |

**The three-phase contract replaces the monolithic `POST /skus/batch` design in the original U3-A report.** See Section 4 for the full contract specification. The Frontend Import Wizard (U3-B4) will call these same endpoints — it is a consumer of the contract, not a separate code path.

#### Frontend Changes (consuming the 3-phase API)

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

### 5.2 Explicitly Out of Scope for MVP

| Feature | Reason |
|---------|--------|
| Image upload/import | Requires file storage infrastructure (S3/CloudBase Storage) — defer to U3-C |
| Barcode scanning | Requires camera API integration — defer to U4 |
| Excel (.xlsx) support | Start with CSV only; add xlsx parsing after core flow works |
| Import templates (save/load mappings) | Nice-to-have, defer |
| Webhook/API-based product sync | Requires external API design — long-term roadmap |
| Product variants (size, flavor) | Requires variant data model design — separate discovery |

### 5.3 U3-B Sub-Slice Breakdown (5 Slices — Backend-First, Contract-First)

The U3-B implementation is split into 5 independently shippable sub-slices. **The ordering is deliberate: the agent-operable API contract comes first, the human-friendly wizard comes later.** Each slice produces a working, testable increment that can be reviewed and merged independently.

---

#### Slice U3-B1: Permission Foundation + Import Run Contract Model (0.5 day)

**Goal:** Seed `skus:import` permission AND design the `import_runs` table contract. **No endpoints, no frontend.**

| Task | File(s) | Notes |
|------|---------|-------|
| Add `skus:import` permission code | `backend/scripts/create_wholesaler.py` | Add `("skus:import", "Import SKUs via preview/validate/apply contract")` to `permissions_data` list |
| Add `skus:import` permission code | `backend/scripts/seed_demo_data.py` | Add `("skus:import", "Import SKUs")` to `PERMISSION_CODES` list |
| Create `import_runs` table migration | `backend/alembic/versions/0xx_import_runs.py` | Schema as defined in Section 4.3 |
| Create `ImportRun` ORM model | New: `backend/models/import_run.py` | Maps to `import_runs` table, with status enum |
| Write design-level tests | `backend/tests/` | Test that bootstrap creates the permission; test that `import_runs` DDL applies cleanly |

**Acceptance criteria:**
- `skus:import` permission exists in tenant `permissions` table after bootstrap
- `admin` role holds `skus:import`
- `import_runs` table exists with all columns from Section 4.3 contract
- No API endpoints or frontend changes in this slice

---

#### Slice U3-B2: Backend Preview + Validate Services (1.5 days)

**Goal:** Working `preview` and `validate` endpoints. **No writes to business tables.** These are read-only safety gates.

| Task | File(s) | Notes |
|------|---------|-------|
| Alembic migration: add `custom_attributes JSONB` to `skus` | `backend/alembic/versions/0xx_sku_custom_attributes.py` | `ALTER TABLE skus ADD COLUMN custom_attributes JSONB DEFAULT '{}'` |
| Update SKU ORM model | `backend/models/sku.py` | Add `custom_attributes` mapped column |
| Update Pydantic schemas | `backend/schemas/sku.py` | Add `custom_attributes` to Create/Update/Read |
| Create import Pydantic schemas | New: `backend/schemas/import_schemas.py` | `ImportPreviewResponse`, `ImportValidateRequest/Response` as defined in Section 4.2 |
| Implement `POST /import/preview` | `backend/api/v1/skus.py` | CSV/JSON input, `chardet` encoding detection, returns `import_id` + columns + sample_rows. Creates `import_runs` row with status `previewed`. **Protected by `RequirePermission("skus:import")`.** |
| Implement `POST /import/{id}/validate` | `backend/api/v1/skus.py` | Accepts mapping JSON, validates all rules (Section 4.2), returns row-level errors/warnings. Updates `import_runs` status. **Protected by `RequirePermission("skus:import")`.** |
| ImportService: `preview()` + `validate()` | New: `backend/services/import_service.py` | CSV parsing + validation logic as pure service methods (testable without HTTP) |
| Unit tests | `backend/tests/` | CSV encoding edge cases, mapping validation, missing required fields, duplicate detection |

**Acceptance criteria:**
- `POST /import/preview` accepts CSV, returns `import_id`, creates `import_runs` row
- `POST /import/{id}/validate` returns structured errors/warnings per Section 4.2
- Both endpoints return 403 without `skus:import`
- **No SKU rows are written to the database by either endpoint**
- Existing `POST /skus` (single create) unchanged

---

#### Slice U3-B3: Backend Apply + Audit (1 day)

**Goal:** Working `apply` endpoint that does the actual write + audit trail.

| Task | File(s) | Notes |
|------|---------|-------|
| Implement `POST /import/{id}/apply` | `backend/api/v1/skus.py` | Accepts `{on_conflict}`, writes SKUs + custom_attributes + inventory_stocks (via `ensure_stock_row()`). Protected by `RequirePermission("skus:import")`. |
| ImportService: `apply()` | `backend/services/import_service.py` | Transaction-managed batch insert with row-level error handling |
| Audit logging on apply | `backend/services/import_service.py` | Writes apply result to `sys_audit_logs.metadata_` (JSONB precedent); updates `import_runs` with final status |
| Unit tests | `backend/tests/` | `on_conflict: skip | error`, partial failure, 403 on missing permission, audit record verification, idempotency (double-apply with skip) |

**Acceptance criteria:**
- `POST /import/{id}/apply` creates SKUs with inventory rows
- Apply only works on validated imports (not on raw `previewed` status)
- Returns created/skipped/errors summary per Section 4.2
- 403 without `skus:import`
- Audit record written to `sys_audit_logs.metadata_` and `import_runs`
- Existing single-SKU creation flow unchanged, still requires `skus:create`

---

#### Slice U3-B4: Frontend Import Wizard (calling the 3-phase API) (2 days)

**Goal:** Human-friendly import wizard that consumes the same preview/validate/apply endpoints used by agents.

| Task | File(s) | Notes |
|------|---------|-------|
| Import service (API wrapper) | New: `frontend/src/services/importService.ts` | `previewCSV()`, `validateMapping()`, `applyImport()` — typed wrappers around the 3-phase API |
| Wizard shell + step navigation | New: `frontend/src/pages/skus/ImportWizard/ImportWizard.tsx` | 3-step wizard state machine (preview → validate → apply) |
| Step 1: Upload & Preview | New: `frontend/src/pages/skus/ImportWizard/Step1Preview.tsx` | Drag-and-drop / click upload, calls `POST /import/preview`, shows raw columns + sample rows |
| Step 2: Map & Validate | New: `frontend/src/pages/skus/ImportWizard/Step2Validate.tsx` | Dropdown selectors mapping CSV columns → Mpango fields + custom attributes. Calls `POST /import/{id}/validate`. Shows error/warning table. Re-validate on mapping change. |
| Step 3: Apply & Results | New: `frontend/src/pages/skus/ImportWizard/Step3Apply.tsx` | Confirmation screen with error/warning summary. Calls `POST /import/{id}/apply`. Shows created/skipped/errors result. |
| Wire from SKU List | `frontend/src/pages/skus/SKUListPage.tsx` | Replace disabled "Import Products" placeholder with working button → opens ImportWizard |

**Acceptance criteria:**
- Human user experiences the same 3-phase flow as an agent calling the API
- Field mapping wizard correctly dispatches CSV columns to Mpango fields
- Validation errors shown before apply is allowed
- Step 2 re-validates when mapping changes
- Results summary shows created/skipped/errored counts

---

#### Slice U3-B5: Custom Attributes in SKU UI (1 day)

**Goal:** Display and edit `custom_attributes` in the existing SKU form and list.

| Task | File(s) | Notes |
|------|---------|-------|
| SKU Form: custom attributes editor | `frontend/src/pages/skus/SKUFormModal.tsx` | Key-value pair editor (add/remove rows) |
| SKU List: optional columns | `frontend/src/pages/skus/SKUListPage.tsx` | Show custom attribute columns when present; toggle visibility |
| Update SKU service | `frontend/src/services/skuService.ts` | Support `custom_attributes` in create/update payloads |

**Acceptance criteria:**
- SKU form shows existing custom attributes and allows editing
- SKU list shows custom attributes as visible columns
- Single SKU creation (non-import) can also set custom attributes

---

### 5.4 Total Effort Summary

| Slice | Duration | Deliverable |
|-------|----------|-------------|
| U3-B1: Permission + Import Run Contract | 0.5 day | `skus:import` seeded, `import_runs` DDL + model |
| U3-B2: Preview + Validate (read-only gates) | 1.5 days | `POST /import/preview`, `POST /import/{id}/validate` |
| U3-B3: Apply + Audit (writes) | 1 day | `POST /import/{id}/apply` with audit trail |
| U3-B4: Frontend Wizard (API consumer) | 2 days | 3-step wizard calling the 3-phase API |
| U3-B5: Custom Attributes UI | 1 day | Custom attributes in SKU form + list |
| **Total** | **6 days** | |

---

## 6. Future Roadmap

### Phase 1 (U3-B1 through U3-B5): Agent-Operable Import + Human Wizard — 6 days
Split into 5 backend-first sub-slices as detailed in Section 5.3: Permission + Contract Model → Preview/Validate → Apply/Audit → Frontend Wizard → Custom Attributes UI.

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

## 7. Risks and Open Questions

### 7.1 Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **CSV encoding issues** (UTF-8 vs Latin-1, BOM headers) | Medium | Use `chardet` for encoding detection; strip BOM on parse |
| **Large file imports** (>1000 rows) blocking | Medium | Batch inserts in chunks of 100; async progress reporting via polling or WebSocket |
| **JSONB query performance** at scale | Low | Current scale (50-500 SKUs/tenant) is trivial for JSONB. Add GIN index if needed later |
| **Field mapping UX complexity** on mobile | Medium | Design mobile-first mapping wizard; use dropdowns instead of drag-and-drop |
| **Migration rollback** if custom_attributes causes issues | Low | JSONB column is nullable with default — safe to add, safe to ignore |
| **Duplicate sku_code handling** in batch | Medium | Support `on_conflict: skip | update | error` strategies — let tenant choose |
| **Data quality** from messy spreadsheets | High | Provide clear validation feedback with row numbers; require manual fix before import |

### 7.2 Open Questions for CTO

1. **Custom attributes scope**: Should custom attributes be searchable/filterable in the product list, or display-only initially? (Recommendation: display-only for MVP, searchable in Phase 5)

2. **Conflict strategy default**: When importing SKUs that already exist, should the default be `skip` or `error`? (Recommendation: `skip` with clear count in results)

3. **Tenant attribute sharing**: Should attribute definitions be shareable across tenants (e.g., a "standard FMCG attribute pack"), or purely per-tenant? (Recommendation: per-tenant for MVP)

4. **Import permission scope**: The existing RBAC system already enforces `skus:read`, `skus:create`, `skus:update` (see Section 1.7). U3-B MUST create a new `skus:import` permission rather than reusing `skus:create`. The rationale: import is a bulk operation with file upload, different error semantics, and higher blast radius — tenants should be able to grant "add products one at a time" without also granting "upload 500 products at once." The `skus:import` permission will be assigned to `admin` at bootstrap. Open question: should `warehouse` also get `skus:import`? (Recommendation: yes — warehouse staff frequently handle stock intake with product data.)

5. **File size limit**: Maximum CSV file size for import? (Recommendation: 5MB / 5000 rows for MVP — covers 95% of target users)

6. **Category standardization**: Should categories be free-text or from a predefined list? Currently free-text. Import would benefit from a category picker or auto-suggest. (Recommendation: keep free-text for MVP, add category management in Phase 5)

7. **Inventory initial quantity**: When importing SKUs, should users also be able to set initial stock quantities in the same import? The `inventory_stocks` row is auto-created at 0. (Recommendation: defer to separate "stock adjustment import" feature — keep SKU import focused on product data)

---

## 8. Exact Files Read

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

### U3-A-R1 Additional Files Read (Permission System)
| File | Purpose |
|------|---------|
| `backend/api/middleware/rbac.py` | `RequirePermission` dependency — enforces `<resource>:<action>` checks |
| `backend/core/governance/roles.py` | Default BI permission matrix, role-action mapping |
| `backend/core/governance/policy.py` | BI policy engine with evaluation order |
| `backend/api/context/auth_context.py` | JWT bearer, token decoding, tenant schema resolution |
| `backend/models/user.py` | User, Role, Permission ORM models (M2M through `user_roles`, `role_permissions`) |
| `backend/api/v1/skus.py` | Existing SKU routes already enforce `skus:read`, `skus:create`, `skus:update` |
| `backend/scripts/create_wholesaler.py` | Full permission list + admin assignment — where `skus:import` must be added |
| `backend/scripts/seed_demo_data.py` | Demo seeder including RBAC — where `skus:import` must be added |

---

## 9. Proposed U3-B Implementation Plan (5 Sub-Slices — Backend-First)

### 9.1 Branch Strategy

```
Branch: codebuddy/u3b-product-csv-import-2026-06-12
Base:   origin/product-dev-recovered
```

### 9.2 Slice U3-B1: Permission + Import Run Contract (0.5 day)

**Commit:** `u3b1_permission_and_contract`

1. Add `("skus:import", "Import SKUs via preview/validate/apply contract")` to `create_wholesaler.py` → `permissions_data` list
2. Add `("skus:import", "Import SKUs")` to `seed_demo_data.py` → `PERMISSION_CODES` list
3. Create Alembic migration for `import_runs` table (DDL from Section 4.3)
4. Create `ImportRun` ORM model (`backend/models/import_run.py`)
5. Design-level tests: verify permission seeded, DDL applies cleanly
6. **No API endpoints, no frontend**

### 9.3 Slice U3-B2: Backend Preview + Validate (1.5 days)

**Commit:** `u3b2_preview_validate`

1. Create Alembic migration adding `custom_attributes JSONB DEFAULT '{}'` to `skus`
2. Update `SKU` model (`backend/models/sku.py`) — add `custom_attributes` column
3. Update Pydantic schemas (`backend/schemas/sku.py`)
4. Create import schemas (`backend/schemas/import_schemas.py`)
5. Implement `POST /api/v1/skus/import/preview` — CSV upload → `import_id` + columns + sample_rows. Creates `import_runs` row. RBAC: `RequirePermission("skus:import")`.
6. Implement `POST /api/v1/skus/import/{import_id}/validate` — accepts mapping → row-level errors/warnings. Updates `import_runs` status. RBAC: `RequirePermission("skus:import")`.
7. `ImportService.preview()` + `ImportService.validate()` service methods
8. Unit tests: CSV edge cases, mapping validation, 403 enforcement
9. **No writes to SKU table — these are read-only safety gates**

### 9.4 Slice U3-B3: Backend Apply + Audit (1 day)

**Commit:** `u3b3_apply_audit`

1. Implement `POST /api/v1/skus/import/{import_id}/apply` — writes SKUs + custom_attributes + inventory (via `ensure_stock_row()`). RBAC: `RequirePermission("skus:import")`.
2. `ImportService.apply()` — transaction-managed batch insert with row-level errors
3. Audit: write apply result to `sys_audit_logs.metadata_` + update `import_runs` final status
4. Unit tests: `on_conflict` strategies, partial failure, 403 enforcement, double-apply idempotency
5. **First slice that writes to business tables**

### 9.5 Slice U3-B4: Frontend Import Wizard (2 days)

**Commit:** `u3b4_frontend_wizard`

1. Create `frontend/src/services/importService.ts` — `previewCSV()`, `validateMapping()`, `applyImport()`
2. Create ImportWizard under `frontend/src/pages/skus/ImportWizard/`:
   - `ImportWizard.tsx` — 3-step state machine
   - `Step1Preview.tsx` — file drop zone → calls `/import/preview`, shows raw columns + sample rows
   - `Step2Validate.tsx` — dropdown mapping → calls `/import/{id}/validate`, shows error/warning table, re-validates on mapping change
   - `Step3Apply.tsx` — confirmation → calls `/import/{id}/apply`, shows created/skipped/errors result
3. Wire from SKUListPage "Import Products" button (replacing disabled placeholder)
4. **The wizard calls the same 3-phase API used by agents/CLI**

### 9.6 Slice U3-B5: Custom Attributes in SKU UI (1 day)

**Commit:** `u3b5_custom_attrs_ui`

1. Update `SKUFormModal.tsx` — key-value pair editor for custom attributes
2. Update `SKUListPage.tsx` — show custom attribute columns, toggle visibility
3. Update `skuService.ts` — support `custom_attributes` in create/update payloads

### 9.7 Validation Commands

```bash
pnpm lint                          # 0 errors
pnpm build                         # pass
git diff --check origin/product-dev-recovered..HEAD  # no whitespace issues
```

### 9.8 Definition of Done

- [ ] `skus:import` permission exists, admin role holds it
- [ ] `import_runs` table exists per tenant schema
- [ ] `POST /import/preview` returns `import_id` + columns + sample rows (no writes to SKU table)
- [ ] `POST /import/{id}/validate` returns structured row-level errors/warnings (no writes)
- [ ] `POST /import/{id}/apply` creates SKUs with inventory rows + audit record
- [ ] All three endpoints return 403 without `skus:import`
- [ ] Frontend wizard calls the same 3-phase API (consumer, not separate code path)
- [ ] Existing single-SKU creation flow unchanged, still requires `skus:create`
- [ ] Agent/CLI can drive the same endpoints without touching the UI
- [ ] Audit record written to `sys_audit_logs.metadata_` and `import_runs` on every apply
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

**End of U3-A-R2 Discovery Report — Awaiting CTO Final Approval**

### R2 Revision Changelog

| Change | Section(s) |
|--------|------------|
| Added Agent-Operable / CLI-Friendly Import Contract (3-phase: preview→validate→apply) | 4 (new) |
| Defined `import_runs` audit table as architecture constraint | 4.3 (new) |
| Added CLI vision (`mpango products import --preview/--validate/--apply`) | 4.4 (new) |
| Added structured JSON response examples for all 3 phases | 4.2 |
| Explained why AI-native Mpango needs an agent-operable contract separate from the human wizard | 4.1 |
| Re-ordered U3-B slices to 5 backend-first slices (B1: Permission+Contract, B2: Preview/Validate, B3: Apply/Audit, B4: Frontend Wizard, B5: Custom Attrs UI) | 5.3, 5.4, 6, 9.2-9.6 |
| Replaced monolithic `POST /skus/batch` with 3-phase `POST /import/preview|validate|apply` | 5.1 |
| Updated Backend Changes table with import run model, audit logging, and 3-phase endpoints | 5.1 |
| Added `import_runs` to Definition of Done | 9.8 |
| Added agent/CLI accessibility to Definition of Done | 9.8 |
| Renumbered all sections (4→5, 5→6, 6→7, 7→8, 8→9) | Throughout |
| No mojibake — all UTF-8 and box-drawing characters confirmed valid | (file scan) |

### R1 Revision Changelog

| Change | Section(s) |
|--------|------------|
| Corrected "no permission gating" claim — RBAC system documented | 1.7 (new), 2.2.7, 7.2.4, 8 (appended) |
| Defined `skus:import` as a new permission (not reuse `skus:create`) | 1.7, 5.1, 5.2, 9.8 |
| Split U3-B into 4 sub-slices (B1: Permission, B2: Backend, B3: Frontend, B4: UI) | 5.3, 6, 9.2-9.5 |
| Removed "Role-based import permissions" from Out of Scope | 5.2 |
| Added sub-slice commit strategy to implementation plan | 9.2-9.5 |
| Added Definition of Done item for 403 on missing `skus:import` | 9.7 |
| No mojibake found — all text confirmed valid UTF-8 / proper box-drawing characters | (file scan) |
