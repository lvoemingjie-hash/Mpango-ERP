# Deploy Path Fix - Mpango ERP v0.1.2-rc1

**Date:** 2026-01-18
**Status:** RESOLVED

## Issue Summary
Production deployment failed with:

```
[ERROR] pyproject.toml not found
```

Root cause was incorrect path assumptions in the deployment script. The backend is located under `backend/`, but the script was checking for `pyproject.toml` and `poetry.lock` in the repository root. Additional path mismatches were found for the bootstrap script and the secrets directory used by docker-compose.

## Root Cause
- Deployment script checked `pyproject.toml` and `poetry.lock` in the repo root instead of `backend/`.
- Bootstrap script check used `scripts/create_wholesaler.py` at root instead of `backend/scripts/`.
- `docker-compose.yml` expects secrets via `${SECRETS_DIR:-./secrets}`; without exporting `SECRETS_DIR`, deployments defaulted to a wrong path in production.

## Fix Applied
- Added `BACKEND_DIR="${APP_DIR}/backend"` in the deployment script.
- Updated checks to `backend/pyproject.toml` and `backend/poetry.lock`.
- Updated bootstrap script check to `backend/scripts/create_wholesaler.py`.
- Exported `SECRETS_DIR` to align with docker-compose env file path.
- Created new script `deploy_v0.1.2-rc1.sh` with corrected headers/report labels.

## Files Updated
- `ai-ledger/ops/deploy_v0.1.1-rc2.sh`
- `ai-ledger/ops/deploy_v0.1.2-rc1.sh`

## Validation Checklist
- ✅ `backend/pyproject.toml` and `backend/poetry.lock` exist.
- ✅ `backend/Dockerfile` uses `WORKDIR /app` and copies `pyproject.toml`/`poetry.lock` correctly.
- ✅ `docker-compose.yml` backend build context is `./backend`.
- ✅ `alembic/` lives under `backend/` and remains accessible inside the container.

## Notes
Re-tagging `v0.1.2-rc1` is required after committing these fixes so that deployment uses the corrected script and paths.
