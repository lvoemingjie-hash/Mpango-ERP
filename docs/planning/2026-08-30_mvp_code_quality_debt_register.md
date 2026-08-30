# DC-12R1 MVP 代码质量债务注册表

**日期：** 2026-08-30
**审计基线：** `origin/product-dev-recovered@24a28d76d6d9483d8101f8e0f537c148dc262859`
**产品代码基线：** `d9dc2e4130ea87a57d433dfadeb2f2736576fac6`
**验证层级：** `V1_SOURCE_ARCHITECTURE_REVIEW`
**声明上限：** `PLANNING_AND_PRE_DELIVERY_GATE_CLASSIFICATION_ONLY`
**状态：** CTO 决策记录；不构成任何产品实现、合并或发布授权

## 1. CTO 结论

Mpango 的核心安全与业务基础明显高于普通原型：租户隔离、SQL 标识符安全、
RBAC、财务不变量、密码恢复中立性和失败即停测试治理均有较强证据。当前主要
风险不是“整体代码不可用”，而是订单/SKU/定价即将汇合时，已有合同漂移和
工程债务可能被新业务复杂度放大。

因此采用三档处理：

1. `MVP_REQUIRED`：交付前必须关闭，未关闭不得进入最终客户旅程或发布裁决。
2. `MVP_NO_GROWTH`：MVP 期间不要求完成全仓重构，但新代码不得继续扩大债务。
3. `POST_MVP`：登记责任与触发条件，MVP 交付后专项治理。

## 2. 交付前必须关闭

| ID | 风险 | 发现与源码锚点 | MVP 关闭条件 |
|---|---|---|---|
| `CQ-ORD-001` | P1 | 订单状态存在双权威。`backend/services/order_service.py:53-75` 声明其为唯一状态变更入口并负责行锁、不变量和账本；但 `backend/api/v1/orders.py:589-621,987-1019` 仍调用 CRUD 路径，`backend/crud/order.py:495-524` 将草稿和已确认订单都直接写为 `CANCELLED`，而 `backend/core/domain/order_state.py:49-72` 区分 `DRAFT -> VOIDED` 与 `CONFIRMED -> CANCELLED`。 | 在 `PRICING-R0` 前冻结唯一生命周期合同；所有订单状态写入统一进入一个领域/应用服务；库存、账本、通知和审计副作用在同一事务边界内；草稿作废、已确认取消、已支付取消/退款均有反例测试；旧 CRUD 直接写状态的可达路径归零。 |
| `CQ-SKU-001` | P1 | 订单行身份合同漂移。`backend/models/order.py:93-125` 文档仍声称 `product_id`，但迁移 `backend/alembic/versions/003_phase_b3_orders_minimal_closed_loop.py:77-79` 已删除该列，`backend/crud/order.py:349-361` 仅保存名称、代码和价格快照。 | 与 `SKU-R0-M1-R1` 同步关闭：订单行采用稳定 `sellable_unit_id` 加不可变快照；legacy 行保持显式 `NULL/legacy`，不得按 `sku_code` 猜测回填；迁移、回滚、跨租户和历史订单测试通过独立审查。 |
| `CQ-CI-001` | P1 | 当前真实集成分支未被主要产品工作流覆盖。`.github/workflows/s5-ci-gate.yml:8-10`、`s1-2-ci-gate.yml:5-7`、`s2-7-ci-gates.yml:8-10` 和 `security-scan.yml:5-7` 只监听 `main/master/develop`；安全工作流还在 `security-scan.yml:57-75` 使用会改写 baseline 的扫描命令并包含可疑 shell 续行。 | `product-dev-recovered` 或其正式 PR 路径具备产品测试、构建和只读密钥扫描；安全扫描不得改写 `.secrets.baseline`；required-check/branch-protection 状态被远端验证。开发期可保留 Lubuntu 手工等价门，但不能替代最终远端强制证据。 |
| `CQ-TEST-001` | P1 | 已知 full-suite 后置残留为 4 wholesalers / 0 registrations / 29 uuid schemas；它降低全量门的可重复性并提高环境归因成本。 | 在最终候选前定位责任测试并关闭，或将确属固定种子的状态写成机器校验的前后基线；fresh full-suite 的任务新增残留必须为零，运行后状态必须与运行前基线精确相等。 |
| `CQ-DEP-001` | P2 | `frontend/package.json:30,40` 重复声明两个不同版本的 `jsdom`，实际解析依赖对象不够明确。 | 保留唯一版本，更新 lockfile，并通过前端全量测试、构建和浏览器 harness 静态门。 |
| `CQ-HE2-001` | P0/P1 | HE2 release validator 仍因 `DEBT-AUTH-CRITICAL-TUPLES` 与 `DEBT-COMMERCE-CRITICAL-TUPLES` 返回阻断状态。 | 对应 inventory、mutation、owner 和证据全部闭合，release validator exit 0；不得把 structural exit 0 提升为 release PASS。 |

## 3. MVP 期间禁止继续增长

| ID | 发现 | 立即约束 | 完整关闭时机 |
|---|---|---|---|
| `CQ-MOD-001` | 当前有 38 个非测试、非 migration 的 backend Python 文件超过 500 行，14 个 frontend 产品文件超过 400 行；`backend/api/v1/orders.py` 为 1134 行，ruff 还全局忽略 `C901`。 | 定价、调价、再次下单和新订单生命周期逻辑必须进入独立 use-case/service/policy 模块；route 仅做适配，不再扩大 `orders.py`；新模块不得新增全局可变状态。 | MVP 后按调用图拆分历史大模块，并逐步恢复复杂度检查。 |
| `CQ-WARN-001` | `backend/pyproject.toml:129-130` 全局屏蔽 deprecation 警告；backend 中有 142 处 `datetime.utcnow()`。 | 新代码必须使用 timezone-aware UTC；不得新增 blanket warning suppression 或 `datetime.utcnow()`。 | MVP 后建立统一时钟抽象并逐模块清理。 |

## 4. MVP 后专项治理

| ID | 债务 | 后续目标 |
|---|---|---|
| `CQ-COV-001` | 测试合同文档提到覆盖率目标，但当前配置/workflow 中未找到可执行的仓库级强制阈值；高风险路径主要由风险清单、focused bundle、mutation 和浏览器 inventory 保护。 | 在不削弱现有风险门的前提下，引入分层覆盖率阈值，优先订单、支付、租户和认证。 |
| `CQ-REPO-001` | 大量历史报告和 ai-ledger 提高可审计性，也增加检索与认知负担。 | 保留不可变证据，建立 current-truth 索引与归档分层，减少活动代理读取过期报告的概率。 |

## 5. 进入与退出规则

1. `CQ-ORD-001` 是 `PRICING-R0` 的进入条件，不允许在双状态权威上叠加调价、
   支付确认或 24 小时自动取消。
2. `CQ-SKU-001` 与 `SKU-R0-M1-R1` 是同一产品闭环，不建立第二套平行身份。
3. `CQ-CI-001`、`CQ-TEST-001`、`CQ-DEP-001` 和 `CQ-HE2-001` 是最终业务
   旅程/VPS/真机验收的进入条件。
4. `CQ-MOD-001` 和 `CQ-WARN-001` 采用新增代码 fail-closed：违反即阻断候选，
   但不要求在当前 MVP 中重写所有历史模块。
5. 每项关闭都需要独立候选、明确 owner、反例测试、证据层级和受控合并；文档
   中的 `PASS` 不能替代源码或运行时证据。

## 6. 本轮边界

本轮只记录源码审阅事实和 CTO 优先级决策。未修改产品代码、测试、workflow、
依赖、lockfile、migration 或治理运行器；未运行产品测试、PG、Redis 或
Playwright；不声称上述问题已修复。
