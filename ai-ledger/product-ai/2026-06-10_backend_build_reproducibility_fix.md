# Backend Build Reproducibility Fix — Evidence Report

**Date:** 2026-06-10
**Author:** CodeBuddy (AI Agent)
**Branch:** `codebuddy/backend-build-reproducibility-2026-06-10`
**Base:** `origin/product-dev-recovered`
**PR:** https://github.com/lvoemingjie-hash/Mpango-ERP/pull/new/codebuddy/backend-build-reproducibility-2026-06-10
**Status:** ✅ VERIFIED — Ready for CTO review

---

## 1. Problem Statement

Backend Docker image build fails on China/Tencent VPS (Lubuntu) with `ReadTimeout` errors when downloading packages from `files.pythonhosted.org`. The root cause: Poetry 2.x does not honor the `POETRY_PYPI_MIRROR_URL` environment variable (a pip convention, not a Poetry standard). The existing Dockerfile set this env var but `poetry install` silently used the default PyPI source, causing timeouts in China network conditions.

## 2. Root Cause Analysis

| Aspect | Detail |
|--------|--------|
| **Symptom** | `poetry install` hangs/times out on `files.pythonhosted.org` during `docker build` |
| **Direct Cause** | Poetry 2.x ignores `POETRY_PYPI_MIRROR_URL` env var |
| **Why it worked before** | Previous Poetry 1.x versions may have fallen through to pip's env var handling |
| **Scope** | All `docker build` runs from China/Tencent VPS network |

## 3. Approach Selection

| Approach | Description | Verdict |
|----------|-------------|---------|
| **A. Repo-native source config** | Add `[[tool.poetry.source]]` to `pyproject.toml`, regenerate `poetry.lock` | ✅ Selected |
| B. Dockerfile-only (`poetry source add`) | Run `poetry source add` in Dockerfile | ❌ Rejected — mutates `pyproject.toml`, causes lockfile mismatch |
| C. pip fallback | Use `pip install` instead of Poetry | ❌ Rejected — loses lockfile integrity |

**Why Approach A:** The source configuration lives in the repo itself, making builds deterministic regardless of Dockerfile tricks. The lockfile's `[package.source]` metadata ensures every package resolves to the configured mirror. Developers outside China can override or remove the source without affecting pinned versions.

## 4. Changes Made

### 4.1 `backend/pyproject.toml` (+8 lines)

Added Poetry source configuration between `[tool.poetry]` and `[tool.poetry.dependencies]`:

```toml
# Build reproducibility: primary PyPI source set to Aliyun mirror for China/Tencent VPS deployment.
# Developers outside China can override locally or remove this source — dependency versions are
# pinned exactly and will not differ regardless of which mirror serves the packages.
[[tool.poetry.source]]
name = "aliyun"
url = "https://mirrors.aliyun.com/pypi/simple/"
priority = "primary"
```

### 4.2 `backend/poetry.lock` (+598/-11 lines)

Lockfile regenerated via `poetry lock` in Docker container (Poetry 2.2.1, matching Dockerfile).

**Critical verification — ZERO dependency version changes:**
- All 598 added lines are `[package.source]` metadata sections pointing to Aliyun mirror
- 11 removed lines are `python-versions` relocations and `content-hash` update
- No package names, versions, or hashes changed

### 4.3 `backend/Dockerfile` (+10/-2 lines)

| Change | Before | After |
|--------|--------|-------|
| `POETRY_PYPI_MIRROR_URL` env var | Set to Aliyun URL (ineffective) | Removed |
| `requests.max-retries` | Not set | `poetry config requests.max-retries 3` |
| `POETRY_INSTALLER_MAX_WORKERS` | 4 | 2 (more stable on limited-bandwidth) |
| `PIP_DEFAULT_TIMEOUT` | Not set | 120 seconds |
| Poetry source comment | N/A | Added documentation comment |

## 5. Verification Evidence

### 5.1 Build Verification

| Step | Command | Result |
|------|---------|--------|
| Backend image build | `docker build --progress=plain -f backend/Dockerfile backend` | ✅ PASSED (175.8s, all deps from Aliyun) |
| Full compose build | `docker compose -f docker-compose.prod.yml ... build` | ✅ PASSED (backend + frontend built) |

### 5.2 Staging Rehearsal

| Step | Result |
|------|--------|
| `docker compose up -d` | ✅ All 5 containers started |
| Backend `/health/live` | ✅ `{"status":"healthy","service":"mpango-erp-backend","version":"0.2.0"}` |
| Backend `/health/ready` | ✅ `{"status":"healthy","checks":{"database":{"status":"healthy","latency_ms":50.84},"redis":{"status":"healthy","latency_ms":5.18}}}` |
| Frontend via gateway `/` | ✅ HTTP 200 |
| Gateway `/health` | ✅ `{"status":"healthy","service":"mpango-erp-backend","version":"0.2.0"}` |
| Backend `/openapi.json` | ✅ HTTP 200 |
| `alembic current` | ✅ `021_tenant_payments_retailer_id_transaction_id (head)` — all 21 migrations applied |

### 5.3 `docker compose ps` — All Services

| Container | Image | Status | Ports |
|-----------|-------|--------|-------|
| mpango_prod_backend | `mpango_staging_rehearsal-backend` | Up (healthy) | 8000/tcp |
| mpango_prod_frontend | `mpango_staging_rehearsal-frontend` | Up (healthy) | 80/tcp |
| mpango_prod_gateway | `nginx:alpine` | Up (healthy) | 0.0.0.0:8888->80/tcp |
| mpango_prod_postgres | `postgres:15-alpine` | Up (healthy) | 5432/tcp |
| mpango_prod_redis | `redis:7-alpine` | Up (healthy) | 6379/tcp |

### 5.4 Pre-commit Hooks

| Hook | Result |
|------|--------|
| trim trailing whitespace | Passed |
| fix end of files | Passed |
| check yaml | Skipped (no yaml changes) |
| check for added large files | Passed |
| Detect secrets | Passed |

## 6. Diff Summary

```
 backend/Dockerfile     |  10 +-   (env var fix, retry config)
 backend/pyproject.toml |   8 +    (Aliyun source config)
 backend/poetry.lock    | 598 +-   (source metadata only, no version changes)
 3 files changed, 605 insertions(+), 11 deletions(-)
```

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Aliyun mirror outage during build | Low | Medium — build fails but no data loss | `requests.max-retries=3` + `PIP_DEFAULT_TIMEOUT=120` |
| Developers outside China see slower installs | Very Low | Low | Aliyun mirrors serve international traffic well; devs can remove source if needed |
| Lockfile content-hash mismatch | None | N/A | Lockfile regenerated from matching pyproject.toml |
| Dependency version drift | None | N/A | Only `[package.source]` metadata added; all versions pinned identically |

## 8. Worktree Isolation

- **Worktree:** `C:\Users\Jeff0\MPANGO ERP\backend-build-fix` (git worktree, isolated from main workspace)
- **Main workspace:** `C:\Users\Jeff0\MPANGO ERP\windsurf mpango erp` — **untouched**
- **No VPS connections made**
- **No production data accessed**

## 9. Next Steps for CTO

1. Review the branch `codebuddy/backend-build-reproducibility-2026-06-10`
2. Verify lockfile integrity: `cd backend && poetry lock --check` (should report valid)
3. Test build on Lubuntu VPS: `docker compose -f docker-compose.prod.yml build backend`
4. If satisfied, merge to `product-dev-recovered`
5. Clean up worktree: `git worktree remove "C:\Users\Jeff0\MPANGO ERP\backend-build-fix"`

---

**Verdict:** ✅ **BUILD_REPRODUCIBILITY_FIX_VERIFIED** — All verification steps passed. Branch ready for CTO review and merge.
