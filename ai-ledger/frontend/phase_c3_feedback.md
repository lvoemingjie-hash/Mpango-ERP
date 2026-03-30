# Phase C3 Feedback  Tenants CRUD & API Consumer Audit

**Date**: 2026-02-13
**Role**: Senior Frontend Engineer (Cascade AI)
**Status**:  Complete

---

## Section 1: Implementation Status

###  Verified CRUD Features

| Feature | Status | Notes |
|---------|--------|-------|
| **List tenants** (GET /wholesalers) |  | Pagination via `page`/`size` params; response body `data.items` + `data.pagination` |
| **Create tenant** (POST /wholesalers) |  | Zod validates `code` client-side (`^[A-Z0-9]+$`, 332 chars) before submit |
| **Edit tenant** (PUT /wholesalers/{id}) |  | Code field disabled on edit; only mutable fields sent |
| **Delete tenant** (DELETE /wholesalers/{id}) |  | Confirmation dialog; soft-delete on backend |
| **409 Conflict handling** |  | Duplicate code shows "A tenant with this code already exists." in modal |
| **403 Forbidden handling** |  | Shows "Permission denied. You need the wholesalers:write permission." |
| **Permission-aware UI** |  | Create/Edit/Delete buttons disabled when user lacks `wholesalers:write` |
| **Auto-refresh after mutation** |  | `fetchTenants(page)` called after create/update/delete success |
| **Loading state** |  | "Loading" shown in table body during fetch |
| **Empty state** |  | "No tenants found." when list is empty |
| **Error banner** |  | Red banner above table on load failure |
| **Server error in modal** |  | Red banner inside form modal on submit failure |
| **Zod  Pydantic alignment** |  | `code`: min 3, max 32, `^[A-Z0-9]+$`; `name`: min 1, max 255 |
| **TypeScript strict** |  | `tsc --noEmit` passes with zero errors |

### Files Modified (This Session)

| File | Change |
|------|--------|
| `src/types/tenant.ts` | Added `schema_name` field to `Tenant` interface |
| `src/pages/tenants/TenantListPage.tsx` | Added permission-aware UI (`canWrite`), improved `extractErrorMessage` for 409/403 |
| `src/pages/tenants/TenantFormModal.tsx` | Confirmed Zod schema matches backend (min 3, max 32, regex) |

---

## Section 2: API Usage Feedback Table (DX/UX Audit)

| # | Issue Type | Endpoint | Description | Impact | Suggestion |
|---|-----------|----------|-------------|--------|------------|
| 1 | **Naming** | GET /wholesalers | Response field `schema_name` is a backend-internal concept (PostgreSQL schema). Frontend never displays it. | Low  unused field in table, adds payload weight | Rename to `tenant_schema` for clarity, or omit from default list response and only include in detail view |
| 2 | **Naming** | All | Backend entity is "Wholesaler", frontend calls it "Tenant". URL path is `/wholesalers`. | Medium  cognitive overhead for new developers | Consider aliasing `/tenants`  `/wholesalers` in API gateway, or document the mapping prominently |
| 3 | **Field Usage** | GET /wholesalers | `address` field is returned but never shown in the list table (only in edit modal). | Low  minor payload waste | No action needed; acceptable for CRUD simplicity |
| 4 | **Chattiness** | Edit flow | Opening Edit modal does NOT require a second `GET /wholesalers/{id}` call  list response already contains all fields needed. |  Positive  efficient design | Good. No extra round-trip needed. |
| 5 | **Error UX** | POST /wholesalers (409) | Backend returns `{"detail": {"code": "WHOLESALER_CODE_EXISTS", "message": "Wholesaler code 'X' already exists"}}`. Structured and parsable. |  Positive  frontend can show exact message | Good. The `code` field enables programmatic handling. |
| 6 | **Error UX** | POST /wholesalers (422) | Pydantic validation errors return `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`  array format differs from 409's object format. | Medium  frontend must handle both array and object `detail` shapes | Standardize error envelope: always use `{"detail": {"code": "...", "message": "..."}}` for all error types |
| 7 | **Pagination** | GET /wholesalers | Supports both `skip/limit` AND `page/size` query params. Dual interface is flexible but potentially confusing. | Low  works fine, but API docs should clarify precedence | Document that `page/size` takes precedence over `skip/limit` when both are provided |
| 8 | **Missing** | All | No `is_active` or `status` field on Wholesaler. Cannot soft-disable a tenant without deleting it. | Medium  no way to "suspend" a tenant | Consider adding `is_active` boolean to Wholesaler model for tenant suspension use case |
| 9 | **Missing** | GET /wholesalers | No search/filter parameter (e.g., `?q=acme`). As tenant count grows, list-only pagination is insufficient. | Medium  will become a problem at scale | Add optional `q` query param for code/name search |
| 10 | **Performance** | GET /wholesalers | Response includes `updated_at` which is not displayed in the table. | Low  negligible | Acceptable; useful for cache invalidation if needed later |

---

## Summary for CTO

### What Works Well
- **Error codes are structured**  `WHOLESALER_CODE_EXISTS` with message is excellent DX
- **No N+1 chattiness**  list response contains all fields needed for edit modal
- **Pagination is in response body**  no need to parse headers

### Recommended Backend Improvements (Priority Order)
1. **Standardize error envelope**  422 validation errors use array format while 409/403/404 use object format
2. **Add search/filter**  `?q=` param for code/name search on list endpoint
3. **Add `is_active` field**  enable tenant suspension without deletion
4. **Document dual pagination**  clarify `page/size` vs `skip/limit` precedence

---

*记录人：Cascade AI (Frontend)*