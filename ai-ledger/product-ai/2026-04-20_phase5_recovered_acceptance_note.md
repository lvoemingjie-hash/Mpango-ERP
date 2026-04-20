# Phase 5 Recovered Branch — Acceptance Note

日期：2026-04-20
分支：`product-dev-recovered`
当前状态：**AUTH BLOCKERS CLEARED**

## 摘要
- 先前 full acceptance 的结论是 **未接受（NOT ACCEPTED）**，主因是两个 auth 回归阻塞了 tenant-scoped 业务流
- 这两个阻塞现已完成窄范围修复并验证通过
- 当前恢复分支已经重新具备：identity `/auth/me`、`select-tenant`、contextual `/auth/me` 的正常链路
- 因此，导致上一轮验收中断的 auth 主阻塞已解除，可以继续恢复后的完整业务验收

## 已修复问题
1. `backend/api/v1/auth.py`
   - `select_tenant()` 已改为使用正确表名：`user_roles`
   - `POST /api/v1/auth/select-tenant` 运行时已恢复为 `200 OK`
2. `backend/api/v1/auth.py` + `backend/schemas/auth.py`
   - identity-only `/auth/me` 不再返回不兼容的 `email=""`
   - 当前返回 `email=null`，并与声明的 schema 兼容

## 已验证结果
- `GET /api/v1/auth/me`（identity token）：**PASS**
- `POST /api/v1/auth/select-tenant`：**PASS**
- `GET /api/v1/auth/me`（contextual token）：**PASS**
- 新增 auth 回归测试：**PASS**
- 现有 JWT 边界测试：**PASS**
- 前端构建：**PASS**

## 下一步
- 在当前补丁基础上继续执行此前被阻断的 wholesaler order / pricing / payment / outstanding balance / payment modal / smoke 验收

## 对应账本
- 原始未通过验收：`ai-ledger/ops/2026-04-20_phase5_recovered_full_acceptance.md`
- 本次 auth 修复账本：`ai-ledger/ops/2026-04-20_phase5_recovered_auth_regression_patch.md`
