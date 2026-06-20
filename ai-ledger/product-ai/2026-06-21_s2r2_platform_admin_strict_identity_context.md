# S2-R2: RequirePlatformAdmin Strict Identity Context Fix

**Date:** 2026-06-21
**Branch:** `codebuddy/s2-r2-platform-admin-strict-identity-context-2026-06-21`
**Base:** `92e1a0d` (S2-R1 HEAD on `codebuddy/s2-r1-platform-super-admin-boundary-2026-06-21`)
**Status:** COMPLETE — strict AND checks applied, 33/33 tests green
**Commit:** `4e92498` — pushed to `origin/codebuddy/s2-r2-platform-admin-strict-identity-context-2026-06-21`

---

## 1. Objective

Fix a reviewer finding in S2-R1's `RequirePlatformAdmin`: the dependency used `TokenPayload.is_identity_only` as a gate condition, but that property uses **OR semantics** (`tenant_id is None OR tenant_schema is None`). A partial-context token — one where `tenant_id` is set but `tenant_schema` is None (or vice versa) — would pass `is_identity_only` and, combined with `is_super_admin`, bypass the platform gate.

**Solution:** Replace the `token.is_identity_only` check with explicit field-level AND checks: `token.tenant_id is None AND token.tenant_schema is None AND token.is_super_admin`.

---

## 2. Reviewer Finding: OR vs AND Security Difference

### `TokenPayload.is_identity_only` (core/security.py:56)

```python
@property
def is_identity_only(self) -> bool:
    return self.tenant_id is None or self.tenant_schema is None
```

This property was designed for the legacy identity/context token distinction — it answers "does this token MAYBE lack full tenant context?" The OR semantics are intentional for that use case: if either field is missing, the token might not have full context, so downstream code should handle it carefully.

**But OR is wrong for a security boundary.** Consider these truth tables:

| tenant_id | tenant_schema | `is_identity_only` (OR) | Strict identity (AND) |
|-----------|---------------|------------------------|----------------------|
| None      | None          | **True**               | **True**             |
| set       | None          | **True** (!)           | False                |
| None      | set           | **True** (!)           | False                |
| set       | set           | False                  | False                |

Rows 2 and 3 are the vulnerability: a partial-context token passes the OR-based check. Under S2-R1, if such a token also carried `super_admin`, it would be allowed through the platform gate.

**Why this matters in practice:**
- A crafted or malformed JWT with a partial payload (one tenant field set, other missing) could bypass the platform boundary.
- Future code that constructs tokens (e.g., during tenant provisioning transitions) might temporarily create partial-context tokens. The strict AND check ensures they can never access platform routes.

### S2-R2 Fix (rbac.py)

```python
# S2-R2: Use explicit field checks, NOT token.is_identity_only.
#
# TokenPayload.is_identity_only is defined as:
#   tenant_id is None OR tenant_schema is None
# This OR semantics is designed for the legacy identity/context token
# distinction, where it signals "this token may not have full tenant
# context." For a PLATFORM SECURITY BOUNDARY, OR is dangerous: a
# crafted or malformed token with tenant_id set but tenant_schema None
# (or vice versa) would pass is_identity_only and bypass the gate.
#
# We require strict AND: both fields must be None.
is_strict_identity = (
    token.tenant_id is None and token.tenant_schema is None
)

if not (is_strict_identity and token.is_super_admin):
    raise HTTPException(403, "PLATFORM_ADMIN_REQUIRED", ...)
```

---

## 3. Changed Files

| File | Change |
|------|--------|
| `backend/api/middleware/rbac.py` | `RequirePlatformAdmin.__call__`: replaced `token.is_identity_only` with explicit `token.tenant_id is None and token.tenant_schema is None`; added explanatory comment |
| `backend/tests/test_route_authorization_policy.py` | Added 2 partial-context boundary tests; updated module and class docstrings |

---

## 4. Test Evidence

### 4.1 Partial-Context: tenant_id set, tenant_schema None + super_admin → 403

```
test_partial_context_tenant_id_set_schema_none_rejected PASSED
```
Token: `TokenPayload(user_id="sa-1", tenant_id="...", tenant_schema=None, roles=["super_admin"])`.
- `token.is_identity_only` returns **True** (OR: False OR True = True) — would have passed S2-R1.
- `token.is_super_admin` returns **True**.
- **S2-R1 result**: ALLOWED (both conditions met).
- **S2-R2 result**: `HTTPException(403, PLATFORM_ADMIN_REQUIRED)` — strict AND catches it.

The test explicitly asserts `token.is_identity_only is True` to prove the old check would have let this through.

### 4.2 Partial-Context: tenant_id None, tenant_schema set + super_admin → 403

```
test_partial_context_tenant_id_none_schema_set_rejected PASSED
```
Token: `TokenPayload(user_id="sa-1", tenant_id=None, tenant_schema="t_abc123", roles=["super_admin"])`.
- `token.is_identity_only` returns **True** (OR: True OR False = True) — would have passed S2-R1.
- Same proof: the test asserts `is_identity_only is True`.

### 4.3 Identity-Only Super Admin Still Allowed

```
test_identity_only_super_admin_allowed PASSED
```
Token: `TokenPayload(user_id="sa-1", roles=["super_admin"])` — both fields None.
- Strict AND: `None is None and None is None` → **True**.
- Result: access granted.

### 4.4 Full Contextual Super Admin Rejected

```
test_contextual_super_admin_rejected PASSED
```
Token: both tenant_id and tenant_schema set + super_admin.
- Strict AND: `set is not None and set is not None` → **False**.
- Result: 403.

### 4.5 Contextual Tenant Admin Rejected

```
test_contextual_tenant_admin_rejected PASSED
```
Token: both fields set, roles=["admin"] (not super_admin).
- Result: 403.

### 4.6 Full Test Suite

```
33 passed, 2 warnings in 25.93s
```

Breakdown: 31 (S2-R1 baseline) + 2 (S2-R2 partial-context tests) = 33.

---

## 5. Explicit Confirmations

| Constraint | Status |
|------------|--------|
| `TokenPayload.is_identity_only` NOT modified | CONFIRMED — unchanged, only RequirePlatformAdmin's usage changed |
| Route authorization harness NOT relaxed | CONFIRMED — 33/33 green, no xfail added |
| `PUBLIC_ALLOWLIST` NOT expanded | CONFIRMED — unchanged |
| No deployment | CONFIRMED — code changes only |
| No push to `product-dev-recovered` | CONFIRMED — branch is `codebuddy/s2-r2-platform-admin-strict-identity-context-2026-06-21` |

---

## 6. Validation Outputs

| Check | Result |
|-------|--------|
| `pytest tests/test_route_authorization_policy.py -q -rxX --tb=short` | 33 passed in 25.93s |
| `git diff --check` | Clean |
| Pre-commit hooks | All passed |

---

## 7. Branch Safety

This branch is based on S2-R1 (`92e1a0d`), which is based on S2 (`5bc3bf8`), which is based on S1 (`738395e`). It tightens the platform auth boundary further. Should NOT be merged to `product-dev-recovered` without CTO code review.

**Merge path:** `codebuddy/s2-r2-platform-admin-strict-identity-context-2026-06-21` → code review → cherry-pick or merge to `product-dev-recovered` (CTO approvals required).
