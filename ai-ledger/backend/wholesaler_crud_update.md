# Wholesaler CRUD Endpoints Update

**Date**: 2026-02-13
**Role**: Senior Backend Engineer (Cascade AI)
**Status**:  Completed

---

## Summary
Implemented standard CRUD endpoints for Wholesaler (Tenant registry) in public schema and registered the router. Added missing schemas, CRUD class, and pagination helpers.

---

##  Deliverable Checks

- [x] **Confirm endpoints are registered in Router**
  - Registered in `backend/api/app.py` with prefix `/api/v1/wholesalers`
- [x] **Confirm GET /wholesalers returns a list**
  - `GET /wholesalers` returns `WholesalerListResponse` with `items` + `pagination`
- [x] **Confirm POST validates Code uniqueness**
  - On duplicate `code`, returns `409` with `WHOLESALER_CODE_EXISTS`

---

## Files Updated

###  New
- `backend/crud/crud_wholesaler.py`
  - CRUDBase implementation for Wholesaler
- `backend/api/v1/wholesalers.py`
  - CRUD endpoints for `/wholesalers`

###  Modified
- `backend/crud/wholesaler.py`
  - Added `get_wholesaler_by_id` and `get_wholesalers_paginated`
- `backend/api/app.py`
  - Registered wholesalers router
- `backend/schemas/wholesaler.py`
  - Added `schema_name` to WholesalerRead
  - Added `WholesalerResponse` + `WholesalerListResponse`
- `backend/schemas/__init__.py`
  - Exported wholesaler schemas
- `backend/crud/__init__.py`
  - Exported `wholesaler` CRUD instance

---

## Endpoints

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/api/v1/wholesalers` | `WholesalerListResponse` | Supports `skip/limit` or `page/size` |
| POST | `/api/v1/wholesalers` | `WholesalerResponse` | Validates unique `code` |
| GET | `/api/v1/wholesalers/{id}` | `WholesalerResponse` | 404 if not found |
| PUT | `/api/v1/wholesalers/{id}` | `WholesalerResponse` | 404 if not found |
| DELETE | `/api/v1/wholesalers/{id}` | `MessageResponse` | Soft delete |

---

## Notes / Alignment

- **Schema alignment**: matches frontend expectations (id, code, name, schema_name, created_at, status fields). `schema_name` is derived by `Wholesaler.get_tenant_schema()`.
- **Pagination**: included metadata via `Pagination` schema for consistency with existing user list endpoints.
- **CORS**: already enabled globally; wholesalers endpoints fall under `/api/v1/*` and are included.

---

*Boot Contract acknowledged. Architecture Constitution > Boot Contract > all other contracts.*