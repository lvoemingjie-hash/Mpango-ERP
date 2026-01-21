# Mpango ERP v0.1.1-rc2 Deployment Status Index

**Last Updated**: 2026-01-15T17:30:00Z
**Version**: v0.1.1-rc2
**Status**: ✅ READY FOR PRODUCTION (with CTO approval)

---

## Deployment Timeline

| Date | Milestone | Status |
|------|-----------|--------|
| 2026-01-14 | RC Validation Round 2 | ✅ COMPLETE |
| 2026-01-15 | Code Review Audit | ✅ COMPLETE |
| 2026-01-15 | CTO Decision (Option C) | ✅ APPROVED |
| 2026-01-15 | Deployment Remediation | ✅ COMPLETE |

---

## v0.1.2-rc1 Failure Log (Date + Name)

- 2026-01-18 - Backend startup failed: circular import in `api.dependencies` (`get_current_user_context`)

## Core Documents

### Deployment Artifacts
- `ai-ledger/ops/deploy_v0.1.1-rc2.sh` - Main deployment script
- `ai-ledger/ops/prod.env.template` - Environment template
- `docker-compose.yml` - Container orchestration

### Deployment Reports
- `ai-ledger/ops/2026-01-15_production_deploy_v0.1.1-rc2.md` - Full deployment report with audit
- `ai-ledger/ops/2026-1-15 Jeff to OPS AI.md` - CTO decision instructions

### Backend Hardening
- `ai-ledger/backend/2026-01-15_v0.1.1-rc2_hardening_alignment.md` - Backend security hardening

### Testing & Validation
- `ai-ledger/test/rc-validation-round2.md` - RC validation round 2
- `ai-ledger/test/Mpango_ERP v0.1代码审查与分析报告.md` - Code review report

---

## Remediation Status Summary

| Priority | Issue | Status | File Modified |
|----------|-------|--------|---------------|
| P0-1 | docker-compose.yml hardcoded credentials | ✅ FIXED | docker-compose.yml |
| P0-2 | deploy script source injection | ✅ FIXED | deploy_v0.1.1-rc2.sh |
| P1-1 | Bootstrap default password | ✅ FIXED | deploy_v0.1.1-rc2.sh |
| P1-2 | Deployment report placeholders | ✅ FIXED | deploy_v0.1.1-rc2.sh |
| P2 | Healthcheck fragile logic | ✅ FIXED | deploy_v0.1.1-rc2.sh |

---

## Sign-off Chain

| Role | Name | Status | Date |
|------|------|--------|------|
| OPS AI | Deployment System | ✅ Complete | 2026-01-15 |
| Test AI | Independent Testing | ✅ PASS | 2026-01-14 |
| Independent Auditor | QA System | ⚠️ Conditional Approval | 2026-01-15 |
| Lead Engineer | Technical Review | ⚠️ Pragmatic Approach | 2026-01-15 |
| CTO | Jeff | ✅ Option C Selected | 2026-01-15 |

---

## Usage Instructions

### Deploy to Production

```bash
# 1. Clone and checkout tag
git fetch --tags
git checkout v0.1.1-rc2

# 2. Create secrets directory
mkdir -p /opt/mpango/secrets
chmod 700 /opt/mpango/secrets

# 3. Create prod.env from template
cp ai-ledger/ops/prod.env.template /opt/mpango/secrets/prod.env
# Edit prod.env with strong passwords

# 4. Run deployment (REQUIRED: --admin-password)
./ai-ledger/ops/deploy_v0.1.1-rc2.sh --admin-password "YourStrongPassword123!"
```

### Rollback Instructions

```bash
cd /opt/mpango/app
git checkout <previous_tag>
docker compose build --no-cache
docker compose down
docker compose up -d
```

---

## Known Limitations (v0.2 Backlog)

- [ ] Redis configured but not yet used for caching
- [ ] No log aggregation (ELK/Loki)
- [ ] No metrics endpoint (/metrics)
- [ ] No automated backup before migrations
- [ ] No container resource limits
- [ ] No SSL/TLS configuration
- [ ] No secrets rotation strategy

---

*This index was auto-generated to track v0.1.1-rc2 deployment status*

## 2026-01-20 – Boot Contract v1 闭环完成

**Date**: 2026-01-20  
**Scope**: Backend service boot chain (local + Docker)  
**Status**: ✅ COMPLETED – Boot Contract v1 closed

---

### Milestone Summary

- Backend 在 **本地非 Docker 环境** 通过 Boot Contract：
  - `poetry run uvicorn main:app --host 0.0.0.0 --port 8000` 启动成功。
  - `curl http://localhost:8000/health` 返回 200，响应体包含 `{"status":"healthy","service":"mpango-erp-backend","version":"0.1.0", ...}`。[file:84]
- Backend 在 **Docker + docker compose 环境** 通过 Boot Contract：
  - `docker compose build backend` 成功构建镜像。
  - `docker compose up backend` 中，`mpango_backend` 正常启动，日志显示：
    - `🚀 Mpango ERP Backend v0.1.0 starting...`
    - `📋 Loading OpenAPI spec from docs/contracts/openapi.yaml`
    - `INFO:     Application startup complete.`
    - `INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)`。[file:84][file:85]
  - 在宿主机执行 `curl http://localhost:8000/health` 返回 200，健康检查 JSON 与本地环境一致。[file:84][file:85]

---

### Involved AIs & Responsibilities

- **Backend AI – Boot Contract Alignment**  
  - 按 `Boot-contract.md` 和 `2026-01-20_boot_contract_alignment.md` 要求，对 backend 启动路径进行约束与修正。[file:81][file:82]
  - 确保本地环境下：
    - FastAPI 应用入口与依赖关系无循环导入；
    - `poetry run uvicorn main:app ...` 可稳定启动；
    - `/health` 健康检查端点返回 200 并携带版本信息。[file:82][file:84]

- **Ops AI – Boot Contract Verification & Packaging Fix**  
  - 在 `2026-01-20_ops_boot_contract_verification.md` 中，以 PLAN / EXECUTION / EVIDENCE 三段式重新验证：本地启动、Docker 构建与运行。[file:84][file:85]
  - 识别并修复 **(c) ops packaging error**：
    - 问题表现：容器内 `.venv` 损坏并尝试重建时，出现  
      `The virtual environment found in /app/.venv seems to be broken.`  
      `Recreating virtualenv mpango-erp-backend in /app/.venv`  
      `[Errno 5] Input/output error: 'pgproto.cp314-win_amd64.pyd'`。[file:84]
    - 根因：Windows 本地虚拟环境 / `.pyd` 文件被打入 Linux 容器，且运行时通过挂载覆盖导致 venv 损坏。[file:64][file:84]
  - 采取的修复措施：
    - 新增 `backend/.dockerignore`，显式排除 `.venv`、缓存与本地二进制文件，避免将 Windows 虚拟环境打入镜像。[file:84]
    - 修改 `backend/Dockerfile` 将安装命令更新为：  
      `RUN poetry install --no-root --no-interaction --no-ansi --no-cache`  
      以强制在 Linux 容器内重新下载干净的依赖。[file:64][file:84]
    - 重新执行：
      - `docker compose build backend`
      - `docker compose up backend`
      - `curl http://localhost:8000/health`  
      并在 ledger 中记录了成功启动日志与健康检查输出。[file:84][file:85]

---

### Evidence (Commands & Logs)

**Local (non-Docker) boot**

- Commands:
  - `cd backend`
  - `poetry run uvicorn main:app --host 0.0.0.0 --port 8000`
  - `curl.exe http://localhost:8000/health`。[file:84]
- Key outputs:
  - `🚀 Mpango ERP Backend v0.1.0 starting...`
  - `📋 Loading OpenAPI spec from docs/contracts/openapi.yaml`
  - `INFO:     Application startup complete.`
  - `INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)`。
  - `{"status":"healthy","service":"mpango-erp-backend","version":"0.1.0",...}`。[file:84]

**Docker boot**

- Commands:
  - `docker compose down -v`
  - `docker compose build backend`
  - `docker compose up backend`
  - `curl http://localhost:8000/health`。[file:84][file:85]
- Key outputs:
  - `mpango_backend  | 🚀 Mpango ERP Backend v0.1.0 starting...`
  - `mpango_backend  | 📋 Loading OpenAPI spec from docs/contracts/openapi.yaml`
  - `mpango_backend  | INFO:     Application startup complete.`
  - `mpango_backend  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)`。[file:84][file:85]
  - `{"status":"healthy","service":"mpango-erp-backend","version":"0.1.0","timestamp":"2026-01-20T06:40:39.994252"}`。[file:84][file:85]

---

### Classification & Lessons Learned

- **Issue classification**:
  - 初始问题：Backend 启动失败（循环导入 + 环境配置混乱）。[file:17][file:65]
  - 最终阻塞点：`(c) ops packaging error` – Windows `.venv` / `.pyd` 与 Linux 容器不兼容导致虚拟环境损坏。[file:84]
- **Process improvements**:
  - 引入 `Boot-contract.md` 与 PLAN / EXECUTION / EVIDENCE 三段式 ledger 作为所有 Backend / Ops 修复的强制约束。[file:81][file:82][file:84]
  - 将本次事件标记为：**“Boot Contract v1 – Backend + Ops 联合闭环完成”**，作为后续版本（v0.1.2 及以后）的启动行为基线。
