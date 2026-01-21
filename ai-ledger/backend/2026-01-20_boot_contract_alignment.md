# Boot Contract Alignment – Backend Startup Verification

**Date**: 2026-01-20  
**Status**: COMPLETED  
**Owner**: Backend AI

---

## PLAN
- 阅读并确认 `boot_contract.md`、`architecture_contract.md`、`api_contract.md` 的约束；记录现有实现与契约差异。  
- 确认本地启动失败的根因：`DATABASE_URL`、`SECRET_KEY` 缺失导致 `Settings` 验证失败；`main.py` 直接导入 `api.v1.*` 和 `api.middleware.*` 违反 Boot Contract。
- 规划修复路径：
  1. 为 `Settings` 提供安全的本地默认值，保证裸环境可启动。  
  2. 抽离应用装配逻辑到新的 `api/app.py`，让 `main.py` 仅负责构建 App 并调用装配函数，符合依赖方向。  
  3. 恢复健康检查依赖的 `get_db_session` helper。  
  4. 全量执行 Boot Contract 命令链验证，并记录输出作为证据。

## EXECUTION
- 更新 `core/config.py`：
  - 使用 `SettingsConfigDict` 指定 `.env`，并为 `DATABASE_URL`、`SECRET_KEY` 提供开发默认值。  
  - 简化模块级 `settings` 暴露方式。
- 新建 `api/app.py`：集中配置 CORS、`AuthenticationMiddleware`、`IdempotencyMiddleware` 以及主业务路由。
- 调整 `main.py`：
  - 仅导入 `core.config.get_settings` 与 `api.app.configure_app`；
  - 符合 Boot Contract 禁止直接导入 `api.middleware.*`、`api.v1.*` 的约束；
  - 在应用实例化后调用 `configure_app(app, settings)`。
- 恢复 `database/session.py::get_db_session` 兼容函数，以供健康检查依赖。
- 本地命令执行（均在 `backend/` 目录）：
  ```powershell
  poetry install --no-root --no-interaction --no-ansi
  poetry run uvicorn main:app --host 0.0.0.0 --port 8000
  powershell -Command "Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/health"
  poetry run python -c "import importlib; [importlib.import_module(m) for m in ['api.context','api.middleware.auth','api.middleware.rbac','api.dependencies']]; print('IMPORT_OK')"
  ```

## EVIDENCE
- `poetry run uvicorn main:app --host 0.0.0.0 --port 8000`
  ```text
  INFO:     Started server process [13116]
  INFO:     Waiting for application startup.
  🚀 Mpango ERP Backend v0.1.0 starting...
  📋 Loading OpenAPI spec from docs/contracts/openapi.yaml
  INFO:     Application startup complete.
  INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
  ```
- `powershell -Command "Invoke-WebRequest -UseBasicParsing -Uri http://localhost:8000/health"`
  ```json
  {"status":"healthy","service":"mpango-erp-backend","version":"0.1.0","timestamp":"2026-01-20T05:54:54.973537"}
  ```
- 导入顺序验证
  ```powershell
  poetry run python -c "import importlib; [importlib.import_module(m) for m in ['api.context','api.middleware.auth','api.middleware.rbac','api.dependencies']]; print('IMPORT_OK')"
  ```
  输出：`IMPORT_OK`

---

*Boot Contract 对齐完成：本地裸环境启动成功，健康检查 200，导入链自检通过。*
