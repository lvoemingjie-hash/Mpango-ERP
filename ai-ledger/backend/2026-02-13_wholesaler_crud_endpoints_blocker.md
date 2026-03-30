# 2026-02-13 14:00  Wholesaler CRUD Endpoints (Track C Frontend Blocker)

## 背景 / 触发
- **Frontend Phase C3** (Tenants 管理) 已完成，但调用 `/api/v1/wholesalers` 全部 404。
- 根因：后端未提供 Wholesaler CRUD 标准接口，仅登录流程存在 `get_wholesaler_by_code`。

## 已完成工作
1. **新增 Wholesaler CRUD Router**
   - `GET /api/v1/wholesalers`（支持 skip/limit + page/size）
   - `POST /api/v1/wholesalers`
   - `GET /api/v1/wholesalers/{id}`
   - `PUT /api/v1/wholesalers/{id}`
   - `DELETE /api/v1/wholesalers/{id}`（软删除）
2. **新增 CRUDBase 实现**：`crud/crud_wholesaler.py`
3. **补齐 schema 响应结构**：`WholesalerResponse`, `WholesalerListResponse`, `schema_name`
4. **接入路由**：`api/app.py` 注册 `/api/v1/wholesalers`
5. **唯一性校验**：`POST` 对 `code` 做唯一检查（返回 409）

## 前端发现到后端未完成事项（已补齐）
-  缺失 `/wholesalers` CRUD 接口（导致 404）
-  缺失 Wholesaler Read response 的 `schema_name`

## 仍需继续完善的后端事项（建议提交 CTO）
1. **RBAC 权限补齐**
   - 目前未定义 `wholesalers:*` 权限码（seed 中无）
   - 建议新增：`wholesalers:read/create/update/delete` 并在路由加 `RequirePermission`
2. **WholesalerCreate 校验增强**
   - 建议在 `schemas/wholesaler.py` 增加 `code` 正则 `^[A-Z0-9]+$` 的 Pydantic 验证
3. **测试覆盖**
   - 增加 `/wholesalers` CRUD 测试用例（含冲突/404/软删除）

## 关联文件
- `backend/api/v1/wholesalers.py`
- `backend/crud/crud_wholesaler.py`
- `backend/crud/wholesaler.py`
- `backend/api/app.py`
- `backend/schemas/wholesaler.py`
- `backend/schemas/__init__.py`

---
*记录人：Cascade AI (Backend)*