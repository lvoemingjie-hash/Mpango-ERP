# Changelog — v0.1.9-contract-polish

**Release**: v0.1.9-contract-polish
**Date**: 2026-02-14
**Type**: Proactive Hardening (no behavior change, no breaking changes)
**Commit**: `fix(sec): apply CTO rulings for v0.1.9 [skip ci]`

---

## Changes

### 1. CamelModel Adapter (API Contract Consistency)

**Files created:**
- `schemas/base.py` — `CamelModel` base class with `AliasGenerator(validation_alias=to_camel)`

**Files modified (Read/Data schemas → CamelModel inheritance):**
- `schemas/wholesaler.py` — `WholesalerRead`
- `schemas/payment.py` — `PaymentData`
- `schemas/order.py` — `Order`, `OrderItem`
- `schemas/user.py` — `UserRead`, `RoleRead`
- `schemas/sku.py` — `SKURead`
- `schemas/inventory.py` — `StockViewRead`
- `schemas/invitation.py` — `InvitationData`, `InvitationLookupData`
- `schemas/retailer.py` — `RetailerData`, `BindingData`
- `schemas/__init__.py` — Added `CamelModel` export

**Why this is hardening, not a bug fix:**
The API already worked with snake_case. This change adds forward-compatible camelCase input acceptance without changing serialization output. It eliminates a class of future integration friction and provides a single inheritance point for all response schemas, preventing per-schema config drift.

**Behavior:**
- Input: accepts BOTH `plan_type` (snake_case) AND `planType` (camelCase)
- Output: remains `plan_type` (snake_case) — **no breaking change**
- When ready to switch output to camelCase: add `serialization_alias=to_camel` to `AliasGenerator`

### 2. Secrets Hygiene (.env.example)

**File modified:**
- `.env.example` — `SECRET_KEY` value changed from `your-secret-key-change-in-production-min-32-chars` to `EXAMPLE_ONLY_REPLACE_WITH_python_c_import_secrets_secrets_token_urlsafe_32`

**Why this is hardening, not a bug fix:**
The previous example value was 50+ characters and could accidentally pass the length validator if copy-pasted. The new value is unmistakably a placeholder, reducing deployment accident risk.

### 3. Test Coverage

**File created:**
- `tests/test_v019_camel_adapter.py` — 17 tests covering:
  - CamelModel base class round-trip (snake→camel→snake)
  - Per-schema camelCase input acceptance (all 12 Read/Data schemas)
  - Serialization output verification (stays snake_case)

### 4. Documentation

**Files created:**
- `docs/SECURITY_POSTURE.md` — Full security posture report including:
  - Permission Coverage Matrix (29 protected + 4 auth-only + 9 public endpoints)
  - Secrets management posture
  - Environment config coverage (21/21 = 100%)
  - Operational robustness (DB pool, health probes, tenant isolation)
- `docs/CHANGELOG_v0.1.9.md` — This file

---

## What Did NOT Change

| Area | Reason |
|------|--------|
| Endpoint logic | No endpoint, service, or repository code modified |
| RBAC enforcement | Already 100% covered (verified in SECURITY_POSTURE.md) |
| Startup validation | Already fail-fast with 8 validators |
| Health probes | Already correct (no business table access) |
| DB pool config | Already parameterized and documented |
| Frontend code | Zero frontend changes required |

## Test Results

```
tests/test_v019_camel_adapter.py  17 passed  0.46s
```

---

## Upgrade Path

1. Apply this version: `git merge v0.1.9-contract-polish`
2. No migration needed — schema-only changes
3. No env changes needed — `.env.example` is documentation only
4. Frontend continues to work unchanged
5. When ready for camelCase output: update `AliasGenerator` in `schemas/base.py`
