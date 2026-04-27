# Payment Runtime Fix — Nested Transaction Conflict

日期：2026-04-27
分支：`product-dev-recovered`
优先级：P0
结论：**FIXED**

---

## 问题描述

`POST /api/v1/payments` 返回 500 错误：

```
sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session.
```

同时 `GET /api/v1/payments` 也返回 500（因缺少 `payments` 表）。

---

## 根因分析

### 1. 嵌套事务冲突（代码缺陷）

**事务所有权链：**
1. `get_tenant_db_session()` → `get_tenant_db()` → `async with AsyncSessionLocal() as session:`
2. `SET LOCAL search_path TO "<tenant_schema>", public` → 隐式开启事务
3. `yield session` → session 返回给端点
4. 端点调用 `PaymentService.create_payment()`
5. `async with tenant_db.begin():` → **尝试在已有事务上再开一个事务** → `InvalidRequestError`

**问题位置：** `backend/services/payment_service.py` 第 67 行

**正确做法：** 事务生命周期由 `get_tenant_db()` generator 统一管理（commit/rollback），service 层不应再调 `begin()`。

### 2. Demo 租户缺少 payments 表（环境问题）

Demo 租户 schema `t_a0000000000040008000000000000001` 缺少 `payments` 表。这不是代码问题，而是 bootstrap 脚本未被完整运行。

---

## 修复内容

### 文件变更

1. **`backend/services/payment_service.py`**
   - 移除 `async with tenant_db.begin():` 及其嵌套缩进
   - 方法体提升一层缩进
   - 事务由 `get_tenant_db()` generator 负责
   - 异常仍会正常传播，generator 的 `except` 块会回滚

2. **`backend/tests/test_payment_atomicity.py`**
   - 更新原有测试：验证 `begin()` 不再被调用（`txn.entered == 0`）
   - 新增测试：验证 cash payment 正确应用 outstanding balance delta
   - 新增测试：验证 `_apply_outstanding_balance_delta` 异常正确传播

### 环境修复

- 在 demo 租户 schema 中创建了 `payments` 表（基于 `bootstrap_tenant_schema.py` 定义，额外添加了 `retailer_id` 和 `transaction_id` 列以匹配 `payment_repository.py` 的查询）

---

## 测试结果

### 单元测试

| 测试文件 | 结果 |
|----------|------|
| `tests/test_payment_atomicity.py` | 2 passed |
| `tests/test_phase5_order_payment.py` | 35 passed, 1 xfail |
| `tests/test_payments_api.py` | 5 passed |

### 运行时验证

| 操作 | 修复前 | 修复后 |
|------|--------|--------|
| `GET /api/v1/payments` | 500 (`UndefinedTableError`) | ✅ 200 |
| `POST /api/v1/payments` (cash) | 500 (`InvalidRequestError`) | ✅ 201 |
| Outstanding balance 更新 | 不可达 | ✅ -200.00 正确 |

### 运行时验证命令

```powershell
# 完整链路验证
Login → Select-tenant → Create Order → Create Payment → Check Balance
```

全部通过。

---

## 事务所有权模型（修复后）

```
get_tenant_db() generator (database/session.py)
  ├── async with AsyncSessionLocal() as session
  ├── SET LOCAL search_path → 隐式开启事务
  ├── yield session → 给端点
  │     └── PaymentService.create_payment()
  │           ├── 不再调用 begin()
  │           ├── 直接使用 session 执行 SQL
  │           └── 异常传播回 generator
  ├── await session.commit()  ← 正常时提交
  └── await session.rollback() ← 异常时回滚
```

---

## 影响分析

- **修改符号：** `PaymentService.create_payment`
- **d=1 直接调用者：** `POST /api/v1/payments` 端点（`backend/api/v1/payments.py`）
- **d=1 内部依赖：** `_apply_outstanding_balance_delta`（private，无外部调用）
- **风险级别：** LOW — 移除嵌套事务不影响业务逻辑，事务安全性由 generator 保证

---

## 相关账本

- 前次验收（发现此问题）：`ai-ledger/ops/2026-04-23_phase5_recovered_full_acceptance_rerun.md`
- Auth 修复补丁：`ai-ledger/ops/2026-04-20_phase5_recovered_auth_regression_patch.md`
