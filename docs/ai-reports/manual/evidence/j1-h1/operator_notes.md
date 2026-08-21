# Operator Notes — J1-H1 Desktop Human Journey

记录人：ZCode（观察/计时/记录）。用户 = 真实操作者。

---

## 环境就绪

2026-08-21 14:21 (+08:00)：预检全部通过（见 runtime_preflight.md），
已向操作者发布就绪消息。

（后续按步骤追加记录）

## Step 1 第 1 次尝试 — HTTP 500（ENVIRONMENT_ONLY）

- 14:22 发布就绪消息；14:29 操作者报告注册提交返回 500。
- 客观证据：后端日志 `asyncpg.exceptions.UndefinedTableError:
  relation "public.tenant_registrations" does not exist`
  （api/v1/auth.py:109 → services/onboarding_service.py:306）。
- 根因：任务数据库（127.0.0.1:29432，来自 backend/.env）从未执行
  `alembic upgrade head`。此前核验 "head 037" 实为 alembic.ini 默认连接
  （端口 5432 的旧开发库），非任务库——预检疏漏，教训：核验迁移必须带
  DATABASE_URL 并直接查询目标库的表清单。
- 修复（环境层，未触碰产品源码/业务数据）：带 DATABASE_URL 执行
  `alembic upgrade head`（需 REPORTING_USER_PASSWORD，已在 .env），迁移至
  head 037，public 29 表，tenant_registrations 已存在，后端 /health 200。
- 分类：ENVIRONMENT_ONLY（本地任务运行时准备缺陷，非产品缺陷）。
- 14:35 修复完成，已请操作者重新尝试 Step 1。


---

## CTO_AUTHORIZED_DIAGNOSTIC_CONTINUATION_AFTER_F13

- 2026-08-21 ~17:55 (+08:00)：CTO 授权选项 B（诊断性继续），条款：
  1. 权威人工旅程已于 Step 5 正式停止，F-13 保持 BLOCKER，不因后续继续改判。
  2. 本段落为唯一授权载体：CTO_AUTHORIZED_DIAGNOSTIC_CONTINUATION_AFTER_F13。
  3. 唯一授权桥接：操作者本人在地址栏手动输入 /invite。
  4. 禁止：代理点击、直接调用 API、修改数据库、预置邀请。
  5. Step 5-12 以后续标记 DIAGNOSTIC 继续，用于发现更多阻塞与摩擦。
  6. 如再次出现必须绕过 UI 才能继续的阻塞：立即停止，不新增第二个桥接。
  7. 最终总裁决固定为 STOP_AND_REPORT_CTO_WITH_REPRODUCIBLE_PRODUCT_BLOCKER；
     报告分列 Authoritative Journey (Step 1-5, 终止于 F-13) 与 CTO-Authorized
     Diagnostic Continuation (经手动 /invite 桥接的 Step 5-12)。
  8. F-13 修复范围控制（CTO 指令）：MVP 必修=侧栏或 Customers 页清晰
     "Invite retailer" 入口+空态 CTA+导航测试；二维码邀请=高价值增强，
     不替代最小修复，需先定义 token 生命周期/防重放/批发商绑定/过期/泄漏合同。
