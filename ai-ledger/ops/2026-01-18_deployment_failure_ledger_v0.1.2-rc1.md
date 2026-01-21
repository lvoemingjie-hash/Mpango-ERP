# Deployment Failure Ledger - Mpango ERP v0.1.2-rc1

**Date**: 2026-01-18
**Status**: HALTED (deployment paused per request)
**Scope**: VPS deployment attempts for tag v0.1.2-rc1

---

## Summary

Production deployment encountered multiple failures across script paths, Docker Compose behavior, secrets parsing, and runtime configuration. Deployment is paused; no further production changes are being made at this time.

---

## Failure Ledger

| ID | Symptom | Root Cause | Impacted Step | Evidence | Status | Recommended Fix |
|----|---------|------------|--------------|----------|--------|-----------------|
| F-001 | `pyproject.toml not found` | Deploy script assumed repo root instead of `backend/` | Step 4 (Build) | `[ERROR] pyproject.toml not found` | RESOLVED in script | Use `BACKEND_DIR=/opt/mpango/app/backend` and check paths under backend/ |
| F-002 | `No such service: --no-cache` | docker-compose build arg order parsed `--no-cache` as service on old compose | Step 4 (Build) | `[ERROR] No such service: --no-cache` | RESOLVED in script | Use `docker-compose build --no-cache backend` |
| F-003 | `POSTGRES_PASSWORD variable is not set` | Missing secret export and placeholder values in prod.env | Step 3/5 | docker-compose warning | RESOLVED in script; may still exist in env | Ensure prod.env uses real values; export `POSTGRES_PASSWORD` before compose |
| F-004 | `/opt/mpango/secrets/prod.env: line 34: ERP: command not found` | `source prod.env` fails on unquoted values containing spaces | Step 3.5 | Shell error on `source` | RESOLVED in script | Avoid `source`; whitelist-export only required vars or quote values |
| F-005 | `pydantic_settings SettingsError` for `CORS_ORIGINS` | env expects JSON list but template provides comma string | Runtime (backend boot) | `error parsing value for field "CORS_ORIGINS"` | UNRESOLVED in template | Use JSON: `CORS_ORIGINS='["https://...","https://..."]'` in prod.env(+template) |
| F-006 | Alembic async driver mismatch | `alembic.ini` uses sync URL while env.py uses async engine | Step 6 (Migrations) | psycopg2/async error | RESOLVED in VPS; pending local | Override `sqlalchemy.url` from `DATABASE_URL` (asyncpg) in env.py |
| F-007 | Poetry venv permission error | bind mount `/app` overrides container venv location | Build/Run | Poetry venv create failure | RESOLVED on VPS (manual) | Remove backend/frontend bind mounts + command overrides in docker-compose.yml |
| F-008 | `KeyError: 'ContainerConfig'` | Stale container metadata with old docker-compose | Step 5 (Postgres up) | Compose traceback | UNRESOLVED | `docker-compose down`, remove old containers (no `-v`), rerun |
| F-009 | `ERROR: No such service: --tail` | Old compose CLI expects `--tail` before service or different syntax | Step 7 (Log fetch) | Compose error | OPEN | Use `docker-compose logs --tail=50 backend` |
| F-010 | Backend failed to start (`get_current_user_context` circular import) | Circular import between `api.dependencies` and `api.middleware.rbac` | Runtime (backend boot) | ImportError trace on startup | OPEN | Refactor dependency imports to break cycle |

---

## Current State

- Deployment halted; no further production changes.
- Script fixes exist locally but tag `v0.1.2-rc1` needs retagging after final confirmation.
- prod.env.template still needs CORS_ORIGINS JSON format update.

---

## Next Steps (Non-Production)

1. Update `ai-ledger/ops/prod.env.template` with JSON-formatted `CORS_ORIGINS`.
2. Consolidate fixes locally and re-tag `v0.1.2-rc1` when approved.
3. Retry deployment only after a clean, reviewed release artifact.

---

*Ledger created to track deployment failures for v0.1.2-rc1.*
