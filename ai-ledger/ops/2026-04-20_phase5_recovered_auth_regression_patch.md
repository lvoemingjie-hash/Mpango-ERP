# Phase 5 Recovered Branch — Auth Regression Patch

日期：2026-04-20
分支：`product-dev-recovered`
范围：仅修复已确认的两个 auth 回归阻塞
结论：**PATCH VERIFIED**（`select-tenant` 已恢复，identity-only `/auth/me` schema mismatch 已解决）

---

## 一、修复目标

根据上一轮验收账本 `ai-ledger/ops/2026-04-20_phase5_recovered_full_acceptance.md`，恢复分支存在两个 P0 认证阻塞：

1. `POST /api/v1/auth/select-tenant`
   - 代码查询了 `user_role`
   - 实际 tenant schema 使用 `user_roles`
2. identity-only `GET /api/v1/auth/me`
   - 代码返回 `email=""`
   - `CurrentUserData.email` 声明为 `EmailStr`
   - 响应模型在 identity-only 场景下不兼容

本次修复要求：仅限这两个点，不做 tenancy/auth 架构扩展。

---

## 二、影响分析

这是认证关键路径修复，业务风险级别高，但代码改动面小。

直接调用/受影响入口：
- `frontend/src/pages/auth/LoginPage.tsx`
- `frontend/src/pages/auth/WorkspaceSelectorPage.tsx`
- `frontend/src/pages/client/ClientLoginPage.tsx`
- `frontend/src/services/authService.ts`

结论：
- `select-tenant` 修复将恢复单租户自动进入、多租户工作区选择、client 登录三条入场链路
- identity-only `/auth/me` 修复将恢复 super admin / identity-only 用户资料读取的声明式兼容性

---

## 三、代码变更

修改文件：
- `backend/api/v1/auth.py`
  - `select_tenant()` 中 `user_role` → `user_roles`
  - identity-only `/auth/me` 返回 `email=None`
- `backend/schemas/auth.py`
  - `CurrentUserData.email` 调整为 `EmailStr | None`
- `frontend/src/types/auth.ts`
  - `CurrentUserData.email` 调整为 `string | null`
- `backend/tests/test_auth_regressions.py`
  - 新增两个最小回归测试

未修改：
- tenancy model
- pricing/order/payment 业务逻辑
- 平台配置/部署结构

---

## 四、测试与验证

### 1) 新增回归测试
执行命令：
```bash
cd backend
poetry run pytest tests/test_auth_regressions.py -q -rA
```

结果：**PASS**
- `test_select_tenant_uses_user_roles_table_and_returns_contextual_tokens`
- `test_get_current_user_identity_token_returns_nullable_email`

### 2) 现有 JWT 边界护栏
执行命令：
```bash
cd backend
poetry run pytest tests/security/test_jwt_boundaries.py -q -rA
```

结果：**PASS (11 passed)**

### 3) 现有 `/auth/me` 缓存测试
执行命令：
```bash
cd backend
poetry run pytest tests/test_s3c_integration.py::test_auth_me_caching -q -rA
```

结果：**PASS (1 passed)**

### 4) 前端类型契约构建验证
执行命令：
```bash
cd frontend
npm run build
```

结果：**PASS**

### 5) 运行时回归验证
执行方式：重建 `backend` 容器后，通过 PowerShell `Invoke-RestMethod` 直接调用接口。

结果：**PASS**

关键结果摘要：
- `GET /readyz` → healthy
- `POST /api/v1/auth/login` → 200，返回 identity token 与 `DEMO001`
- `GET /api/v1/auth/me`（identity token）→ 200，返回：
  ```json
  {"email": null, "tenant_id": null, "tenant_schema": null}
  ```
- `POST /api/v1/auth/select-tenant` → 200，成功返回 contextual token
- `GET /api/v1/auth/me`（contextual token）→ 200，返回真实用户资料与权限列表

---

## 五、修复结论

明确结论：
- **`select-tenant` is restored**
- **identity-only `/auth/me` schema mismatch is resolved**

这次修复已移除上一轮 full acceptance 的 auth 主阻塞。

注意：
- 本账本只证明 auth blocker 已修复并经回归验证通过
- tenant-scoped 的 wholesaler order / pricing / payment / balance / modal / smoke 项，需要在此基础上继续补跑完整验收
