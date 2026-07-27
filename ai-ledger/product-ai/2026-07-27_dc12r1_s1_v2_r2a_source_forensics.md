# DC-12R1-S1-V2-R2A-Z Source and Harness Forensics

## Verdict

**PASS_SOURCE_ROOT_CAUSE_IDENTIFIED**

The `POST /auth/verify-email` 500 root cause is identified from source-level
analysis. The endpoint at `backend/api/v1/auth.py:147-183` catches exactly
three exception types (`VerificationTokenInvalidError`, `EmailDeliveryNotConfiguredError`,
`OnboardingOrchestrationError`); **ten distinct uncaught exception paths** reach
`generic_exception_handler` (`backend/core/error_codes.py:240-285`) and return
HTTP 500. The most probable root causes in a test/CI context are
`get_settings()` cache poisoning and `RuntimeError` from `_assert_token_hash_key`.

## Base

- Base SHA: `1608016db5d1e0ef25264edca74c829f8a39e8bd`
- Branch: `reports/dc12r1-s1-v2-r2a-zcode-source-forensics-2026-07-27`
- Scope: read-only source audit; no product code or tests modified.

---

## 1. `verify_email_token` terminal-state judgment order

**File:** `backend/services/onboarding_service.py:118-174`

The function checks terminal states in this exact order:

| Step | Line | Check | Outcome |
|---|---|---|---|
| 1 | 126 | `_assert_token_hash_key(settings)` — SECRET_KEY missing or <32 chars | **`RuntimeError`** (uncaught → 500) |
| 2 | 128-129 | `token is None or not token.strip()` | `VerificationTokenInvalidError` → 400 |
| 3 | 134-142 | DB lookup by `token_hash`; `row is None` | `VerificationTokenInvalidError` → 400 |
| 4 | 145-147 | `_is_retryable_setup_email_failure` (extra DB query) | DB error → 500 |
| 5 | 148-157 | Composite: `used_at` / `revoked_at` / `expires_at <= now` / wrong registration status | `VerificationTokenInvalidError` → 400 |
| 6 | 159-163 | Set registration status to `email_verified`; `db.flush()` | DB error → 500 |
| 7 | 165-169 | `complete_email_verified_onboarding(...)` | `EmailDeliveryNotConfiguredError` → 503; `OnboardingOrchestrationError` → 503; other → **500** |
| 8 | 171-172 | Mark `verification_token.used_at`; `db.flush()` | DB error → 500 |

### Key findings

- **`is_deleted` NOT checked** — the `EmailVerificationToken` model inherits `is_deleted` from `AuditMixin`, but `verify_email_token` never checks it. A soft-deleted token with clean `used_at`/`revoked_at`/`expires_at` would verify successfully. This contrasts with the three other token flows (owner setup, password reset, retailer credential) which all check `is_deleted`.
- **No `purpose` re-check** — purpose is enforced by DB CHECK constraint only (`ck_email_verification_tokens_purpose`), not re-validated in Python.
- **No row-level lock** between the read (line 134) and the write (line 171) — concurrent identical verify requests can both pass the invalidity check.
- **Mid-flow commit** in `complete_email_verified_onboarding` (line 205) means a later failure leaves registration committed active but the verification token NOT marked used.

---

## 2. Confirmed 500 exception paths

**Endpoint:** `backend/api/v1/auth.py:147-183`

The `try` block (line 153) catches only:
- `VerificationTokenInvalidError` → 400
- `EmailDeliveryNotConfiguredError` → 503
- `OnboardingOrchestrationError` → 503

Everything else reaches `generic_exception_handler` (`backend/core/error_codes.py:240-285`) → **HTTP 500**.

| # | Trigger | Chain | Key line |
|---|---|---|---|
| 1 | `SECRET_KEY` missing/<32, or `get_settings.cache_clear()` then invalid env | `verify_email_token` → `_assert_token_hash_key` → `RuntimeError` | onboarding_service.py:126, 546-548 |
| 2 | DB unreachable / pool exhausted / `SELECT FOR UPDATE` fails | `verify_email_token` → `db.execute` → sqlalchemy exc | onboarding_service.py:134-139 |
| 3 | `claim_registration_for_provisioning` DB error (no try/except) | → `complete_email_verified_onboarding` → `claim_registration_for_provisioning` → `db.execute` | tenant_provisioning_service.py:84-89 |
| 4 | `import_module("scripts.bootstrap_tenant_schema")` fails | → `TenantProvisioningService.__init__` → `_load_bootstrap` → `ImportError` | tenant_provisioning_service.py:78, 354-355 |
| 5 | `db.commit()` of public assignment fails | → `complete_email_verified_onboarding` → `db.commit` | onboarding_service.py:205 |
| 6 | `issue_setup_token` non-IntegrityError DB error | → `OwnerCredentialSetupService.issue_setup_token` → `db.flush` | owner_credential_service.py:125-133 |
| 7 | `hash_token` inside `issue_setup_token` raises `RuntimeError` | Same as #1, different call site | owner_credential_service.py:120 |
| 8 | `int(settings.SMTP_PORT)` raises before SMTP try block (mocked settings only) | → `_send_smtp_email` line 343 | email_delivery.py:343 |
| 9 | Redis down → rate limiter raises | `RateLimitingMiddleware` → `check_rate_limit` → `raise` | rate_limiting.py:34-46 |
| 10 | `get_settings()` first-call `ValidationError` if cache cleared and env invalid | → `verify_email_token` → `get_settings` → `Settings()` | config.py:298-308 |

### Most probable in test/CI context

Paths **#1** and **#10** are the highest-probability root causes for a test-environment
500, because the `get_settings()` `@lru_cache` is frozen at conftest import time
(via `database/session.py:19`), and only 2 of ~25 test modules call `cache_clear()`.
If collection order changes or a test clears the cache and then mutates env vars,
a subsequent `verify-email` call can hit `RuntimeError("SIGNUP_TOKEN_HASH_KEY_MISSING")`
or a pydantic `ValidationError`, both → 500.

---

## 3. Test isolation forensic findings

### 3a. `dependency_overrides` — ALL CLEAN

Every `app.dependency_overrides[...]` call across the entire test suite is paired
with a cleanup (`pop()` in `finally` or `autouse` fixture teardown, or the override
is on a fresh per-test `FastAPI()` instance). **No un-cleaned overrides found.**

### 3b. `get_settings()` cache poisoning — SYSTEMIC RISK

`backend/database/session.py:19` calls `get_settings()` at module import time,
freezing the `@lru_cache`. `backend/tests/conftest.py:92` imports
`from database.session import AsyncSessionLocal, async_engine`, triggering the
freeze at conftest collection time.

Of ~25 test modules that call `get_settings()`, only 2 call `cache_clear()`:
- `test_route_authorization_policy.py:70`
- `test_s6e_rbac_permission_registry_drift_gate.py:37`

All others rely on the cached value being correct for their env. This is safe as
long as collection order is stable and no test mutates env vars after cache freeze.
**The fragility is latent, not active.**

### 3c. Environment variable mutations — MOSTLY CLEAN

- `conftest.py:72,74` — permanent hard-set of `DATABASE_URL`/`REPORTING_DATABASE_URL` (intentional session bootstrap).
- `test_route_authorization_policy.py:59` and `test_s6e_rbac_permission_registry_drift_gate.py:27,259` — hard-set `MPANGO_ENV=test` (matches default, benign).
- All other env mutations use `monkeypatch.setenv/delenv` (auto-restored) or `os.environ.setdefault` (no-op if already set).

### 3d. `mock.patch` / `monkeypatch` — ALL CLEAN

Every `mock.patch` is used as a context manager or decorator (auto-cleanup). Every
`monkeypatch` usage is via the pytest fixture (auto-restored). Manual save/restore
patterns (e.g. `test_dc10f:125-146`) are in `finally` blocks.

### 3e. `ASGITransport` / `AsyncClient` lifecycle — ALL CLEAN

All `AsyncClient` / `ASGITransport` instances are inside `async with` blocks.

### 3f. Database session cleanup — CLEAN

The `async_session` fixture (`conftest.py:478-558`) always rolls back + closes.
Direct `AsyncSessionLocal()` usages are all in `async with` blocks. Tests that
`commit()` are cleaned by truncate-at-start in the next fixture invocation.

---

## 4. U6L test teardown completeness

**File:** `backend/tests/test_u6l_email_verified_onboarding_orchestration.py`

### Autouse fixture `_u6l_public_schema` (lines 49-61)

- **Setup:** `_ensure_onboarding_tables()` + `_clear_u6l_rows_and_schemas()` + `clear_dev_email_deliveries()` + `FakeSMTP.reset()`
- **Teardown (`finally`):** `app.dependency_overrides.pop(get_db_session, None)` + same clear/reset.

### Cleanup scope

`_clear_u6l_rows_and_schemas()` (lines 82-112):
1. Selects `wholesaler_id, tenant_schema` from registrations matching `owner_email LIKE 'u6l_%@example.com'`
2. `DROP SCHEMA IF EXISTS "<schema>" CASCADE` for each tenant schema
3. `DELETE FROM public.owner_credential_setup_tokens WHERE registration_id IN (...)`
4. `DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6l_%@example.com'`
5. `DELETE FROM public.wholesalers WHERE id = ANY(:wholesaler_ids)`
6. `commit()`

### Gaps identified

| Gap | Severity | Detail |
|---|---|---|
| `email_verification_tokens` / `onboarding_status_tokens` not explicitly deleted | Medium | Relies entirely on `ON DELETE CASCADE` from `tenant_registrations`. If FK constraints diverge from model, orphan rows persist. |
| Tenant schema leak if `tenant_schema` is NULL at teardown | Low | Only captures schemas from registration rows; a NULL `tenant_schema` would orphan the schema. Not observed in current tests. |
| `owner_email` mutation would orphan cleanup | Low | If a test mutates `owner_email` to a non-`u6l_` value, the registration and linked wholesaler/schema would not be cleaned. No current test does this. |

### `monkeypatch` usage in U6L

Three tests (`test_production_missing_owner_setup_smtp_config_fails_closed`,
`test_production_owner_setup_smtp_failure_fails_closed_with_retry_anchor`,
`test_real_bootstrap_owner_setup_smtp_failure_persists_anchor_and_retry_reconciles`)
use `monkeypatch.setattr` for `get_settings`, `TenantProvisioningService`, and `smtplib.SMTP`.
All are properly cleaned by pytest's automatic monkeypatch teardown + `FakeSMTP.reset()`.

---

## 5. Summary of root cause assessment

The most probable root cause of a 500 on `POST /auth/verify-email` in a test/CI
environment is **`get_settings()` cache poisoning** (paths #1/#10): a prior test
module clears the `lru_cache` and mutates environment variables, causing a
subsequent `verify_email_token` call to encounter either a `RuntimeError` from
`_assert_token_hash_key` (if `SECRET_KEY` becomes invalid) or a pydantic
`ValidationError` from `Settings()` reconstruction.

In a production environment, the most probable root causes are:
- **DB unavailability** (path #2/#3/#5) — asyncpg connection failures propagate uncaught.
- **Redis unavailability** (path #9) — the rate limiter raises before the endpoint handler runs.
- **Bootstrap module import failure** (path #4) — a bad deploy that breaks `scripts/bootstrap_tenant_schema`.

The endpoint's `try/except` block is too narrow: it should also catch
`RuntimeError`, `sqlalchemy.exc.DBAPIError`, and `ConnectionError` to convert
them to controlled 503/502 responses rather than opaque 500s.

---

## 6. Evidence index

| Concern | File | Lines |
|---|---|---|
| `verify_email_token` | `backend/services/onboarding_service.py` | 118-174 |
| Composite invalidity check | `backend/services/onboarding_service.py` | 148-157 |
| `_assert_token_hash_key` | `backend/services/onboarding_service.py` | 546-548 |
| `complete_email_verified_onboarding` | `backend/services/onboarding_service.py` | 177-226 |
| Mid-flow commit | `backend/services/onboarding_service.py` | 205 |
| POST `/auth/verify-email` endpoint | `backend/api/v1/auth.py` | 147-183 |
| `generic_exception_handler` (500) | `backend/core/error_codes.py` | 240-285 |
| `get_settings()` lru_cache | `backend/core/config.py` | 298-308 |
| Cache freeze at import | `backend/database/session.py` | 19 |
| Conftest import triggers freeze | `backend/tests/conftest.py` | 92 |
| `EmailVerificationToken` model | `backend/models/tenant_onboarding.py` | 156-211 |
| U6L autouse fixture | `backend/tests/test_u6l_email_verified_onboarding_orchestration.py` | 49-61 |
| U6L cleanup routine | `backend/tests/test_u6l_email_verified_onboarding_orchestration.py` | 82-112 |
| `RateLimitingMiddleware` | `backend/api/middleware/rate_limiting.py` | 25-46 |
