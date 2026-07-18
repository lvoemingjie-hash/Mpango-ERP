# DC-11T4-A Exact Post-Merge Cross-Environment Gate Report

**Date:** 2026-07-18T12:40:36Z (Asia/Shanghai: 20:40)
**Target SHA:** `6daa32bf3fd41b37ac53205b86764df757e2e4c7`
**Branch:** origin/product-dev-recovered
**Environment:** Ubuntu Linux (worktree-based), PostgreSQL 16 (port 5433), Redis 7 (port 6380)
**Python:** 3.12 | **bcrypt:** 4.0.1 | **passlib:** 1.7.4

---

## Verdict: `STOP_AND_REPORT_CTO`

---

## Gate Results Summary

| Gate | Status | Detail |
|------|--------|--------|
| 1. HEAD == exact SHA | ✅ PASS | Confirmed `6daa32bf` |
| 2. Worktree clean | ✅ PASS | `git diff --check` clean, no tracked changes |
| 3. alembic upgrade head | ✅ PASS | All migrations applied |
| 4. alembic current == heads | ✅ PASS | `034_platform_operators`, exactly one head |
| **5. pytest (full backend)** | **❌ FAIL** | 2792 collected, **1 collection error** |
| 6. Critical repeat bundle | ⏳ SKIPPED | Blocked by Gate 5 failure |
| 7. Frontend (vitest + build) | ⏳ SKIPPED | Blocked by Gate 5 failure |
| 8. git diff-check + secrets scan | ⏳ SKIPPED | Blocked by Gate 5 failure |
| 9. gitnexus analyze + status | ⏳ SKIPPED | Blocked by Gate 5 failure |
| 10. Cleanup | ⏳ PENDING | Awaiting instruction |

---

## Gate 5 — Detailed Failure Analysis

### Collection Error

```
ERROR tests/test_u6i4_first_admin_rbac_creation.py
  ValueError: password cannot be longer than 72 bytes, truncate manually if necessary
```

### Root Cause Classification: **Code Defect (bcrypt/passlib incompatibility)**

**Call chain:**

1. `tests/test_u6i4_first_admin_rbac_creation.py:11` → imports `hash_password` from `core.security`
2. `core/security.py:248` → `hash_password()` uses `pwd_context.hash()` with passlib's bcrypt handler
3. At module **import time** (not test execution), the test file invokes `hash_password("OwnerSetup123!")` in a default fixture argument (`tests/test_u6i4_first_admin_rbac_creation.py:121`)
4. passlib 1.7.4's bcrypt handler (`passlib/handlers/bcrypt.py:380`) calls `detect_wrap_bug()` during initialization
5. `detect_wrap_bug()` internally calls `_bcrypt.hashpw(secret, config)` where `secret` is a **probe string longer than 72 bytes**
6. **bcrypt 4.0.1** enforces the 72-byte limit **at the C extension level** (`ValueError: password cannot be longer than 72 bytes`)
7. passlib 1.7.4 predates bcrypt 4.x's strict enforcement — the `detect_wrap_bug` probe was written when bcrypt silently truncated

**Why it fails at collection, not execution:**

The password hashing context (`pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")`) triggers the wrap-bug detection probe **at module import**, which happens during test collection when pytest imports the conftest chain → `core.security` → passlib → bcrypt.

### Secondary Issue (non-blocking, cosmetic)

```
WARNING: passlib.handlers.bcrypt - (trapped) error reading bcrypt version
  AttributeError: module 'bcrypt' has no attribute '__about__'
```

bcrypt 4.0 removed `__about__` attribute; passlib 1.7.4 still tries to read it for version detection. This is a **known incompatibility** between passlib 1.7.4 and bcrypt >= 4.0.

### Why This Cannot Be Fixed Under Task Rules

Task rules explicitly state:
> "不修改代码、测试、迁移、配置或 lockfile"

Possible fixes all require code or dependency changes:
- **Option A:** Pin `bcrypt<4.0.0` in `pyproject.toml` (lockfile change)
- **Option B:** Upgrade passlib to a bcrypt 4.x-compatible fork (dependency change)
- **Option C:** Pre-truncate the probe in test fixture or use `bcrypt` directly instead of passlib (code change)
- **Option D:** Set passlib config to skip wrap-bug probe (config change)

None are permissible under the current task scope.

---

## Environment Configuration Notes

During Gate 5, two additional environment-level validation errors were encountered (resolved by injecting env vars at runtime, not by modifying files):

1. **DATABASE_URL** — Settings validator rejects `postgresql+asyncpg://` prefix; requires `postgresql://`
2. **SECRET_KEY** — Settings validator rejects strings containing `secret` substring; the `.env.example` placeholder was being picked up

These were bypassed via inline environment variables. They indicate that the default `.env` template does not produce a valid test environment without manual overrides.

---

## Other Observed Warnings (non-blocking)

| Warning | Location | Severity |
|---------|----------|----------|
| `datetime.utcnow()` deprecated | `core/structured_logging.py:89` | LOW |
| `declarative_base()` moved in SQLAlchemy 2.0 | `database/base.py:7` | LOW |
| `PytestCollectionWarning: class has __init__` | `test_idempotency.py:32`, `test_s3c_cache.py:20` | LOW |
| `DeprecationWarning: 'crypt' module deprecated` | passlib (Python 3.13 removal) | LOW |

---

## Recommendation

1. **Immediate (unblocks merge):** Pin `bcrypt>=4.0,<4.1` in `pyproject.toml` AND replace passlib usage in `core/security.py` with direct `bcrypt.hashpw()` / `bcrypt.checkpw()` calls. passlib 1.7.4 is unmaintained and has multiple bcrypt 4.x incompatibilities.

2. **Alternative (minimal change):** Pin `bcrypt==3.2.2` to revert to the last version that silently truncates. This is a **band-aid** — passlib remains unmaintained.

3. **Test infrastructure:** Add a CI-level guard that tests can collect with a fresh venv. The current failure is a dependency resolution gap, not a test logic bug.

4. **Settings validation:** Consider relaxing the `DATABASE_URL` validator to also accept `postgresql+asyncpg://` prefix, or document that async URLs must be split into `DATABASE_URL` (sync) + `ASYNC_DATABASE_URL` (async) pattern.

---

## Infrastructure Used (for reproducibility)

```
Worktree:     /home/ivy/MPANGO/dc11t4a-wt
PostgreSQL:   dc11t4a-pg  (0.0.0.0:5433 → 5432)
Redis:        dc11t4a-redis (0.0.0.0:6380 → 6379)
Python venv:  backend/.venv (Python 3.12)
Test command: DATABASE_URL="postgresql://..." SECRET_KEY="..." REDIS_URL="redis://..." poetry run pytest -q
```

---

*Report generated under task DC-11T4-A rules. No code was modified.*
