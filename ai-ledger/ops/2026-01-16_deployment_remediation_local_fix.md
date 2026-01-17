# v0.1.1-rc2 Deployment Remediation - Local Fix Log

**Date**: 2026-01-16
**Branch**: hotfix/backend-v0.1.0-rc2
**Status**: RESOLVED - Alembic verified in container

---

## Tasks Completed

### ✅ Task 1: Switch to hotfix branch
- Branch: `hotfix/backend-v0.1.0-rc2`
- Status: Completed

### ✅ Task 2: Fix deployment script Alembic call

**File**: `ai-ledger/ops/deploy_v0.1.1-rc2.sh`

**Before**:
```bash
docker compose run --rm --entrypoint "" backend \
    python -m alembic upgrade head
```

**After**:
```bash
docker-compose run --rm --entrypoint "" backend \
    sh -c "cd /app && poetry run alembic upgrade head"
```

### ✅ Task 3: Poetry lock validation
- Command: `poetry lock`
- Status: Completed (with package-mode warning)
- Note: poetry.lock exists and contains alembic 1.18.1

### ✅ Task 4: Dockerfile optimization

**File**: `backend/Dockerfile`

**Changes**:
1. Fix Poetry venv creation:
   ```bash
   # Before
   POETRY_VENV_IN_PROJECT=1

   # After
   POETRY_VIRTUALENVS_IN_PROJECT=1
   ```

2. Install deps consistently in Docker:
   ```bash
   RUN poetry install --no-root --no-interaction --no-ansi
   ```

3. Healthcheck moved to `/health/ready`:
   ```bash
   HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
     CMD curl -f http://localhost:8000/health/ready || exit 1
   ```

### ✅ Task 5: Local self-check

**Build Result**: ✅ SUCCESS
```
docker-compose build backend
Successfully tagged windsurfmpangoerp-backend:latest
```

**Alembic Check**: ✅ PASSED
```bash
docker run --rm windsurfmpangoerp-backend poetry run python -m pip show alembic
Name: alembic
Version: 1.18.1
Location: /app/.venv/lib/python3.11/site-packages
```

---

## Findings (Root Cause)
- Alembic was missing because Poetry never created a virtualenv in the container. The Dockerfile used `POETRY_VENV_IN_PROJECT`, which is not a valid Poetry env var, so the install fell back to a non-venv layout and later checks for alembic failed.

## Fix Applied
- Dockerfile: set `POETRY_VIRTUALENVS_IN_PROJECT=1` and install deps with `poetry install --no-root --no-interaction --no-ansi`.

## Verification
- `poetry env info` in the container shows venv at `/app/.venv` (valid).
- `poetry run python -m pip show alembic` succeeds and shows alembic installed in `/app/.venv/lib/python3.11/site-packages`.

## Next Steps
- Re-run migrations using `docker-compose run --rm --entrypoint "" backend sh -c "cd /app && poetry run alembic upgrade head"`.
- Proceed with VPS deployment.

---

## Files Modified

| File | Change |
|------|--------|
| `ai-ledger/ops/deploy_v0.1.1-rc2.sh` | Fixed Alembic call with `poetry run` |
| `backend/Dockerfile` | Fix Poetry venv env var, install flags, update healthcheck |

---

*Log created: 2026-01-16T15:05:00Z*
*Updated: 2026-01-16T16:05:00Z*
*Status: RESOLVED - Alembic available in container*
