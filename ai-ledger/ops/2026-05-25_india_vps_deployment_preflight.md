# Sprint R-1 India VPS Deployment Preflight

**Date**: 2026-05-25
**Scope**: VPS Deployment Preflight Audit & Plan
**Branch**: product-dev-recovered
**HEAD Commit**: b30784b176b2acd59bfdf0602196fb9b0abe3d6a
**Git Status**: clean except untracked preflight ledger
**Note**: 本轮无产品代码修改、无部署、无 VPS 连接、无清理操作。

## 1. VPS Inventory Checklist
Before any deployment or cleanup actions, the following inventory MUST be snapshotted on the target India VPS:
- **OS**: Version and architecture
- **Docker**: Docker daemon version and running status
- **Compose**: Docker Compose plugin version and availability
- **Disk**: Available disk space (e.g., `df -h`)
- **Ports**: Active and listening ports (e.g., `netstat -tuln` or `ss -tuln`)
- **Containers**: All running and stopped containers (`docker ps -a`)
- **Images**: All Docker images (`docker images`)
- **Volumes**: All Docker volumes (`docker volume ls`)
- **Networks**: All Docker networks (`docker network ls`)
- **Non-Mpango Services**: Explicitly identify and document any co-hosted services (e.g., Sing-Box or other applications) that must remain untouched.

## 2. 安全清理原则 (Safe Cleanup Principles)
- **Targeted Cleanup**: Only Mpango ERP related resources are allowed to be removed.
- **Forbidden Commands**: `docker system prune` is strictly prohibited.
- **Volume Protection**: Deleting volumes is strictly prohibited unless a complete database backup has been performed, verified, and explicitly approved by the CTO.
- **Dry-run First**: A dry-run must be executed to preview changes before applying any destructive cleanup.

## 3. 部署脚本恢复/重写计划 (Deployment Script Recovery/Rewrite Plan)
**Status**: The historical deployment and cleanup scripts are MISSING from the current `product-dev-recovered` branch (`scripts/deploy_vps.sh` and `scripts/safe_cleanup_vps.sh` were not found).
**Plan**:
1. **Restore or Rewrite `safe_cleanup_vps.sh`**:
   - Must implement safe cleanup principles (filtering by `name=mpango`).
   - Must include a `--dry-run` flag.
2. **Restore or Rewrite `deploy_vps.sh`**:
   - Must automate `.env.prod` checking, `git pull`, and `docker compose up -d --build`.
   - Must not commit `.env.prod` or any secrets to the repository.
   - Do NOT execute the rewrite or deployment until the CTO approves this plan.

## 4. 数据库迁移原则 (Database Migration Principles)
- **Normal Execution**: Always run `alembic upgrade head` to execute all pending migrations.
- **No Skipping**: Never skip migrations by stamping the Alembic version (`alembic stamp`). Bypassing migrations is strictly prohibited.

## 5. reporting_user / schema 权限检查项 (Reporting User & Schema Permissions)
- Ensure `reporting_role` (used by Dashboard API) is granted `USAGE` privilege on all tenant schemas (e.g., `GRANT USAGE ON SCHEMA <tenant_schema> TO reporting_role;`).
- This must be verified post-migration to prevent `UndefinedTableError` for reporting views like `mv_sales_daily`.

## 6. 部署后验证清单 (Post-Deployment Verification Checklist)
Once deployed, the following must be verified:
- **App Import**: Ensure the application loads without frontend bundle errors.
- **健康检查 (Health Check)**: Verify `/health` and `/health/live` endpoints return 200 OK.
- **登录 (Login)**: Successfully authenticate via `/auth/login` and `/auth/select-tenant`.
- **订单 (Orders)**: Verify orders list loads correctly.
- **信用支付 (Credit Payment)**: Ensure credit payment workflows function as expected.
- **应收 (Accounts Receivable)**: Verify the Finance Accounts Receivable page displays total receivables, credit exposure, and unpaid orders correctly.
- **还款 (Repayment)**: Test the collection/repayment return flow.
- **Ghost QA 浏览器验证 (Browser Validation)**: Conduct Tier 2/Tier 3 Ghost QA exploratory testing to validate state recovery and browser-based UX.

## 7. Stop Conditions
Operations **MUST STOP** and report immediately to the CTO if any of the following occur:
- Any destructive operation is triggered or required outside of the approved Mpango cleanup scope.
- There is any risk to production data (e.g., backup failure, unexpected volume deletion).
- Required deployment or cleanup scripts are missing or fail their dry-run.
- Database migration errors or inconsistencies (e.g., Alembic version mismatch).
- Permission anomalies (e.g., `reporting_user` lacks schema access).
