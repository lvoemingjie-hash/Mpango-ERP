# DC-11T4A-H1 Clean Dependency Provenance Report

**Date:** 2026-07-20
**Target SHA:** 6daa32bf3fd41b37ac53205b86764df757e2e4c7
**Worktree:** `/home/ivy/MPANGO/dc11t4a-h1-fresh`
**Origin:** `https://rykardo-bot@github.com/lvoemingjie-hash/Mpango-ERP.git`

## Step 1: Repository Verification

- **Origin URL:** `https://rykardo-bot@github.com/lvoemingjie-hash/Mpango-ERP.git`
- **Target SHA exists:** Yes — `6daa32b merge(DC-11T2): stabilize test infrastructure contracts`

## Step 2: Worktree at Target SHA

- **HEAD:** `6daa32bf3fd41b37ac53205b86764df757e2e4c7`
- **Status:** Clean worktree at exact target SHA

## Step 3: Poetry Venv from poetry.lock

- **Command:** `POETRY_VIRTUALENVS_IN_PROJECT=true poetry install --sync --no-interaction`
- **Note:** System keyring backend unavailable (KWallet/SecretService not functional on headless server). Keyring disabled via `POETRY_KEYRING_ENABLED=false` to allow install to proceed. This is a documented workaround for headless Linux environments.
- **Python:** 3.12.3
- **Virtualenv:** `/home/ivy/MPANGO/dc11t4a-h1-fresh/backend/.venv`
- **Packages installed:** 256

## Step 4: Sanitized Evidence

### Python Executable Path
```
/home/ivy/MPANGO/dc11t4a-h1-fresh/backend/.venv/bin/python
```

### bcrypt Module
- **__file__:** `/home/ivy/MPANGO/dc11t4a-h1-fresh/backend/.venv/lib/python3.12/site-packages/bcrypt/__init__.py`
- **__version__:** 4.0.1

### importlib.metadata Versions
- **bcrypt:** 4.0.1
- **passlib:** 1.7.4

### poetry show bcrypt
```
 name         : bcrypt
 version      : 4.0.1
 description  : Modern password hashing for your software and your servers
required by
 - passlib requires >=3.1.0
```

### poetry show passlib
```
 name         : passlib
 version      : 1.7.4
 description  : comprehensive password hashing framework supporting over 30 schemes
dependencies
 - bcrypt >=3.1.0
```

### poetry run pip check
```
No broken requirements found.
```

## Step 5: Probes

### bcrypt synthetic 73-byte input
```
ACCEPTED
```
73-byte payload (bcrypt max boundary) hashed and verified successfully.

### Passlib synthetic short-password hash
```
PASS
```
Passlib bcrypt scheme hashed and verified a single-character password.

### import core.security
```
PASS
```
Module imported successfully (with test environment variables).

## Step 6: Test Collection

```
poetry run pytest tests/test_u6i4_first_admin_rbac_creation.py --collect-only -q
```

**Result:** 9 tests collected in 3.18s

- test_create_first_admin_user_role_permissions_and_mappings
- test_first_admin_creation_is_idempotent_without_duplicate_rbac
- test_reconciles_existing_owner_user_with_provided_hash_and_missing_rbac
- test_cross_tenant_isolation_only_writes_requested_schema
- test_fail_closed_for_missing_absent_invalid_schema_or_missing_hash[setup0-3]
- test_no_public_endpoint_placeholder_password_or_provisioning_behavior_change

**Warning:** `passlib/utils/__init__.py:854: DeprecationWarning: 'crypt' is deprecated and slated for removal in Python 3.13`

## Dependency Chain Summary

| Package | Version | Source |
|---------|---------|--------|
| bcrypt | 4.0.1 | poetry.lock (Aliyun mirror) |
| passlib | 1.7.4 | poetry.lock (Aliyun mirror) |

- bcrypt 4.0.1 is a pre-built wheel (no C compilation required)
- passlib 1.7.4 depends on bcrypt >=3.1.0
- No direct bcrypt C extension implementation in project code
- pip check reports zero broken requirements

## Verdict

**PASS_DC11T4A_H1_DEPENDENCY_PROVENANCE**
