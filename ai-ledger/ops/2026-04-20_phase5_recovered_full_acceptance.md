# Phase 5 恢复分支全量验收

日期：2026-04-20
分支：`product-dev-recovered`
环境：本地 Docker Compose（`backend=http://localhost:8000`，`gateway=http://localhost`，`frontend` 由 gateway 暴露）
结论：**NOT ACCEPTED**（存在 P0 运行时阻塞，无法进入租户上下文）

---

## 一、执行目标

对恢复后的 Phase 5 产品线执行全量验收，只找问题，不改代码，不 push，不 merge，不改历史。

本次要求覆盖：
- Backend boot / health
- Auth login
- Tenant selection
- Wholesaler order creation flow
- Pricing flow
- Payment recording flow
- Outstanding balance correctness
- Route-level payment validation status
- Frontend payment modal behavior
- Regression smoke（order list / payments read / inventory core paths）

---

## 二、环境与基线

### 1) 分支与工作区
- 当前分支：`product-dev-recovered`
- 相关分支现状：
  - `product-dev-backup`
  - `product-dev-recovered`
- `git status --short` 结果：仅存在既有未跟踪 ledger 文件；本次验收未引入额外产品代码修改

### 2) 容器状态
执行命令：
```bash
docker compose ps
```

结果：
- `mpango_backend`：Up (healthy)
- `mpango_frontend`：Up (healthy)
- `mpango_gateway`：Up
- `mpango_postgres`：Up (healthy)
- `mpango_redis`：Up (healthy)

### 3) 数据库环境证据
执行命令：
```bash
docker compose exec -T postgres sh -lc "env | sort | grep POSTGRES"
```

结果：
```text
POSTGRES_DB=mpango_erp
POSTGRES_PASSWORD=MpangoDBV0.1.4
POSTGRES_USER=mpango
```

---

## 三、运行时验证与证据

### 1) Backend boot / health
执行方式：PowerShell `Invoke-RestMethod`

验证端点：
```text
GET http://localhost:8000/healthz
GET http://localhost:8000/readyz
GET http://localhost/healthz
```

结果：**PASS**
- `healthz`：healthy
- `readyz`：healthy
  - database：healthy
  - redis：healthy
- gateway `/healthz`：healthy

关键返回：
```json
{"status":"healthy","service":"mpango-erp-backend","version":"0.2.0"}
```

### 2) Auth login
执行请求：
```http
POST /api/v1/auth/login
Content-Type: application/json

{ "email": "admin@mpango.demo", "password": "DemoAdmin2026!" }
```

结果：**PASS**
- 状态码：`200 OK`
- 返回 identity token
- 返回 `roles=["admin"]`
- 返回 `available_tenants=[DEMO001]`

关键返回摘要：
```json
{
  "success": true,
  "data": {
    "user_id": "e4ef947d-610b-4557-a6e4-93e4317f32b9",
    "roles": ["admin"],
    "available_tenants": [
      {
        "id": "a0000000-0000-4000-8000-000000000001",
        "code": "DEMO001",
        "name": "Mpango Demo Wholesaler"
      }
    ]
  }
}
```

### 3) Tenant selection
执行请求：
```http
POST /api/v1/auth/select-tenant
Authorization: Bearer <identity_token>
Content-Type: application/json

{ "tenant_id": "a0000000-0000-4000-8000-000000000001" }
```

结果：**FAIL — P0 blocker**
- 状态码：`500 Internal Server Error`
- 统一错误体：
```json
{
  "code": "INTERNAL_SERVER_ERROR",
  "message": "An internal server error occurred. Please contact support."
}
```

后端日志证据：
```text
sqlalchemy.exc.ProgrammingError: (sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError)
<class 'asyncpg.exceptions.UndefinedTableError'>:
relation "t_a0000000000040008000000000000001.user_role" does not exist
```

数据库证据：
执行命令：
```bash
docker compose exec -T postgres psql -U mpango -d mpango_erp -c "select schemaname, tablename from pg_tables where schemaname='t_a0000000000040008000000000000001' and tablename in ('user_role','user_roles') order by tablename;"
```

结果：
```text
schemaname                             | tablename
---------------------------------------+-----------
t_a0000000000040008000000000000001     | user_roles
```

代码定位结论：
- `backend/api/v1/auth.py` 的 `select_tenant()` 使用了 `user_role`（单数）
- 仓库迁移、模型、seed、tenant bootstrap 全部使用 `user_roles`（复数）
- 该问题确认为**代码缺陷**，不是环境漂移

### 4) Identity `/auth/me`
执行请求：
```http
GET /api/v1/auth/me
Authorization: Bearer <identity_token>
```

结果：**FAIL — 独立代码问题**
- 状态码：`500 Internal Server Error`
- 错误体：
```json
{
  "code": "INTERNAL_SERVER_ERROR",
  "message": "An internal server error occurred. Please contact support."
}
```

代码阅读结论：
- `backend/api/v1/auth.py` 在 identity-only 分支返回：`email=""`
- `backend/schemas/auth.py` 中 `CurrentUserData.email` 类型是 `EmailStr`
- 因此 identity-only `/auth/me` 存在响应模型校验风险，属于**第二个独立代码缺陷**

---

## 四、前端独立验证

### 1) 前端源码构建
执行命令：
```bash
cd frontend
npm run build
```

结果：**PASS**
- `tsc && vite build` 成功
- `1225 modules transformed`
- 产物生成成功

备注：
- 存在 Vite chunk size warning（`index-Btj91Cax.js` > 500kB）
- 这是性能/拆包提示，不是构建失败，也不是本次阻塞项

### 2) 登录页与租户选择页逻辑
代码阅读结论：
- `frontend/src/pages/auth/LoginPage.tsx`
  - 若 `available_tenants.length === 1`，前端会**自动调用** `selectTenant()`
  - 成功后再调用 contextual `/auth/me`
- `frontend/src/pages/auth/WorkspaceSelectorPage.tsx`
  - 多租户场景下用户手动选工作区，也会调用 `selectTenant()` 再调用 `/auth/me`

因此：
- 当前后端 `select-tenant` 500 会直接阻断前端进入业务页面
- 即使绕过该点，identity-only `/auth/me` 仍有独立 500 风险

### 3) Frontend payment modal behavior
结果：**PARTIAL（源码/构建通过，运行时未完成）**

已验证源码：
- `frontend/src/router/AppRouter.tsx` 注册了 `/orders`、`/payments`、`/pricing`
- `frontend/src/pages/orders/OrderListPage.tsx`
  - 存在 `Record Payment` 按钮
  - 打开 modal 前会调用 `paymentService.getByOrder(order.id)` 计算已付金额与剩余余额
- `frontend/src/components/ui/PaymentRecordModal.tsx`
  - 要求 `amount > 0`
  - 要求 `amount <= remainingAmount`
  - 显示 full / partial payment 提示
  - 表单状态与按钮禁用逻辑完整

运行时状态：
- **未能实际点击验证**，因为前端登录后无法完成 tenant context 建立

---

## 五、全量验收结果矩阵

| 项目 | 状态 | 分类 | 说明 |
|------|------|------|------|
| Backend boot / health | ✅ PASS | Runtime | `/healthz`、`/readyz`、gateway `/healthz` 全部正常 |
| Auth login | ✅ PASS | Runtime | demo 登录成功，返回 identity token 与 DEMO001 |
| Tenant selection | ❌ FAIL | Runtime + Code blocker | `select-tenant` 500；根因是 `user_role` 表名错误 |
| Wholesaler order creation flow | ⛔ BLOCKED | Upstream runtime blocker | 无法获得 contextual token，无法进入批发业务流 |
| Pricing flow | ⛔ BLOCKED | Upstream runtime blocker | 无法完成 tenant-scoped pricing API 调用 |
| Payment recording flow | ⛔ BLOCKED | Upstream runtime blocker | 无法进入订单页并建立租户上下文 |
| Outstanding balance correctness | ⛔ BLOCKED | Upstream runtime blocker | 运行时未能完成；前后端相关代码已存在 |
| Route-level payment validation status | ⛔ BLOCKED | Upstream runtime blocker | Phase 5 代码/测试资产存在，但当前环境缺少 pytest 无法补跑自动测试 |
| Frontend payment modal behavior | ⚠️ PARTIAL | Source/build verified | 源码与构建通过，运行时被 auth blocker 卡住 |
| Regression smoke — order list | ⛔ BLOCKED | Upstream runtime blocker | 路由存在，但无法进入应用 |
| Regression smoke — payments read | ⛔ BLOCKED | Upstream runtime blocker | `/payments` 页面与服务调用存在，但无法进入应用 |
| Regression smoke — inventory core paths | ⛔ BLOCKED | Upstream runtime blocker | 需要 contextual auth |

---

## 六、附加环境限制（如实记录）

### 1) 后端测试未能补跑
尝试命令：
```bash
docker compose exec -T backend bash -lc "python -m pytest ..."
cd backend && python -m pytest ...
```

结果：
```text
No module named pytest
```

结论：
- 当前 backend 容器与本机 Python 环境都没有 `pytest`
- 因此本次不能在“不改环境/不安装依赖”的前提下补跑现有后端自动化测试
- 这是**环境限制**，不是对 Phase 5 代码本身的正向证明或反证

### 2) 前端容器不提供 npm
尝试命令：
```bash
docker compose exec -T frontend sh -lc "npm run build"
```

结果：
```text
sh: npm: not found
```

结论：
- frontend 容器是运行态镜像，不是构建态开发环境
- 于是改用工作区本机 Node 环境完成 `npm run build`

---

## 七、根因归类

### A. 运行时主阻塞（P0）
- `POST /api/v1/auth/select-tenant` 500
- 直接阻断所有需要租户上下文的业务验收项

### B. 已确认代码缺陷
1. `backend/api/v1/auth.py`
   - `select_tenant()` 查询写成 `user_role`
   - 正确表名应为 `user_roles`
2. `backend/api/v1/auth.py` + `backend/schemas/auth.py`
   - identity-only `/auth/me` 返回 `email=""`
   - `CurrentUserData.email` 为 `EmailStr`
   - 存在独立 500 风险

### C. 非阻塞项
- 前端构建成功
- 支付 modal 与订单 / 支付 / 定价路由均存在
- Vite chunk size warning 仅为性能提示

---

## 八、最终结论

**本次全量验收结论：NOT ACCEPTED**

原因：
- 恢复分支已成功启动，健康检查通过，登录通过，前端源码可成功构建
- 但租户选择是进入业务应用的前置条件，而该步骤当前稳定返回 500
- 因此所有 tenant-scoped 的核心业务验收项均被 P0 阻塞，不能认定通过

建议后续动作（不在本次执行范围内）：
1. 修复 `select_tenant()` 中 `user_role` → `user_roles`
2. 修复 identity-only `/auth/me` 的响应模型不匹配
3. 在修复后重新执行本 ledger 中被 BLOCKED 的全部运行时验收项
