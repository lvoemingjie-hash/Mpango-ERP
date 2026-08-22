# DC-12R1-MVP-L1-J1-H2-B-R1 — 忘记密码扫描级静默路径闭合（R0 裁决作废重审）

- 日期：2026-08-23（+08:00）
- 执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r1-password-reset-scan-closure-2026-08-23`
  （自 R0 提交 `93382cb2f81f1e02ef26f6ed31e4bd323d5367f5` 创建）
- 裁决目标：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R1_MERGE_REVIEW`

## 0. R0 裁决声明：已被本 R1 取代（superseded）

- R0 台账（`2026-08-22_dc12r1_mvp_l1_j1_h2b_forgot_password_runtime_closure.md`）
  面向 `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R0_MERGE_REVIEW` 的 PASS 主张
  **作废**：R0 只闭合了**端点级**可观测性（`auth.py` forgot_password 的裸
  `except Exception` 分支获得了结构化日志/指标），服务内
  `_enumerate_active_tenant_users` 的**逐租户扫描静默路径仍然开放**——
  SAVEPOINT `except Exception: continue` 把 schema/查询失败吞掉后，调用方
  拿到的是定论式 `issued=False`（"账户不存在"）或定论式"token 无效"，
  内部零事件。R0 台账宣称"可观测性缺口本身是真实缺陷"，但只修了端点
  一层；扫描一层的同类缺口被遗漏。
- 准确表述（沿用 R0 已证事实）：H1 的历史触发数据**不可追溯**——本任务
  不声称复现了 H1 事故本身；R0 闭合的范围仅限端点级可观测性。R1 补齐
  扫描级缺口，且该缺口作为**可复现漏洞类别**在本任务中被确定性证明
  （见 Phase 1）。
- R0 台账事实性错误更正：其 Phase 2 段落声称修改了
  `backend/core/prometheus_metrics.py`（"新增内部失败计数器"）。**该声称
  为假**：R0 提交 93382cb2 实际只改 3 个文件（台账/auth.py/测试），计数器
  定义在 `auth.py` 模块内（`_password_reset_internal_failures_total`），
  `prometheus_metrics.py` 从未被触碰。R1 保持该设计（指标不集中化，
  `prometheus_metrics.py` 仍零改动）。

## 1. 三层事实区分（更正要求 #6）

| 层 | 内容 | 证据状态 |
|---|---|---|
| 历史事故（H1） | 三次提交中性 200、token 恒 0、无错误线索 | 触发数据不可追溯；只能吻合症状，不能复现触发 |
| 可复现漏洞类别 | 扫描期 per-tenant 失败被静默吞掉 → 定论式"账户不存在/无效"，内部零事件 | R1 T9/T4/T10 在 R0 代码上确定性 RED（见 Phase 1） |
| 已实施修复（R1） | 类型化扫描结果/错误 + 端点事件类 + 中性信封不变 + 重放收紧 | 本任务全部 GREEN + 突变 RED 证明 |

## Phase 1 — 可复现漏洞类别的真 PostgreSQL 证明

方法（更正要求 #4）：真实 PG16 + 真实 ASGI app + 真实 HTTP 端点；目标
租户的**已提交 users 表被改名**（`users` → `users_evidence_*`）使其对扫描
不可达——**底层用户证据不删除**（改名表内行数=1 全程断言），失败源于
扫描而非用户缺失；修复（改回表名）后同一邮箱立即恢复发行，证明无损。

- 候选前（R0 代码 93382cb2 + 新测试）RED：T4（无 partial 遥测）、
  T9（零内部事件——静默）、T10（consume 路径无事件）3 项失败，
  其余 7 项通过（R0 已闭合的端点级行为保持）。
- R1 代码 GREEN：10/10。
- 失败注入不是 monkeypatch 假因果：真实 DDL（RENAME TABLE）产生真实
  `UndefinedTableError`，经真实 SAVEPOINT 回滚，被真实端点处理。

## Phase 2 — 有界修复（allowlist 严格 4 文件）

**变更文件（精确清单，共 4 个路径；`prometheus_metrics.py` 不在其中）：**

1. `backend/services/password_reset_service.py`
   - 新增 `TenantUserScanResult`（rows + scanned_schema_count +
     failed_schema_count，仅聚合计数，不含 schema 名/SQL/email）；
   - 新增 `PasswordResetScanIncompleteError`（构造即脱敏：只携带两个
     整数计数；不链入原始异常——驱动错误可内嵌 schema 名）；
   - `_enumerate_active_tenant_users` **保留逐租户 SAVEPOINT 隔离**，
     失败改为计数上抛（不再静默）；
   - `request_reset`：未找到用户 且 failed_schema_count>0 → 抛类型化
     incomplete-scan 错误（绝不把扫描失败定论为"账户不存在"）；找到
     用户 → 结果携带 `scan_failed_schema_count`（内部遥测，不改公开
     信封）；完全成功且无账户 → 仍 issued=False，**零内部事件**；
   - `consume_reset`：零副本 且 failed_schema_count>0 → 抛同一类型化
     错误（在标记 used 之前 → 端点回滚 → token 保持可重试），否则
     行为不变。
2. `backend/api/v1/auth.py`
   - forgot_password 新增 `PASSWORD_RESET_SCAN_INCOMPLETE` 分支：恰一次
     结构化日志（event_class/phase/request_id/failed_schema_count/
     scanned_schema_count）+ 指标 +1 + 回滚 + **公开信封同一中性 200**；
   - 成功路径上 `scan_failed_schema_count>0` → 恰一次
     `PASSWORD_RESET_SCAN_PARTIAL` 遥测（warning 日志 + 指标；发行
     不受影响）；
   - reset_password 新增同错误分支：内部事件 + 回滚（token 未消费）+
     **既有中性 401 INVALID 信封**（公开形状零变化）；
   - 指标仍为 R0 定义于本文件的
     `mpango_password_reset_internal_failures_total{event_class}`，
     label 值域从 2 扩到 4（固定白名单：
     EMAIL_DELIVERY_NOT_CONFIGURED / UNEXPECTED /
     PASSWORD_RESET_SCAN_INCOMPLETE / PASSWORD_RESET_SCAN_PARTIAL）。
   - 日志/指标载荷脱敏：只有固定事件类、phase、request_id、整数计数、
     异常类型名——**无 email/schema/SQL/token/凭据**（测试断言字符串
     不含 email、schema 名、SELECT 片段）。
3. `backend/tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py`
   （重写为 10 测试，见 Phase 3）。
4. `ai-ledger/product-ai/2026-08-23_dc12r1_mvp_l1_j1_h2b_r1_password_reset_scan_closure.md`
   （本台账）。

无迁移/模型/依赖/lockfile/部署/前端变更；`backend/core/prometheus_metrics.py`
零改动。

## Phase 3 — 必需行为 ↔ 测试映射（更正要求 #3）

| 必需行为 | 测试 | 断言要点 |
|---|---|---|
| 全部扫描成功 + 无账户 | T3 | 中性 200、零 token/邮件、**零内部事件**（日志 0 调用、四类指标增量全 0） |
| 目标租户扫描失败 | T9 | 中性 200、零 token/邮件、**恰 1 次** SCAN_INCOMPLETE 事件（日志 1 条 + 指标 +1，其他类增量 0）；证据保留（改名表行数=1）；改回表名 → 恢复发行（无损证明） |
| 无关租户失败 + 目标后来找到 | T4 | 恰 1 token + 1 邮件 + 恰 1 次 SCAN_PARTIAL 遥测（warning 1 条 + 指标 +1，载荷脱敏）；无毒化 |
| 健康官方生命周期账户 | T2 | signup→verify-email→setup-credential（全真实端点）后：中性 200 + token+1 + 邮件 1 |
| 重放收紧（更正 #5） | T7 | 重放**恰 401** + code=INVALID_OR_EXPIRED_PASSWORD_RESET_TOKEN；used_at 置位且跨重放不变（再重放仍 401）；重放密码未施加到任何租户副本（每副本 verify(首密码)=True 且 verify(重放密码)=False） |
| consume 路径扫描失败 | T10 | 有效 token + 全副本不可达 → 中性 401 + 恰 1 事件 + token 未消费（used_at NULL）；修复后同一 token 重置成功 |

（T1/T5/T6/T8 保留 R0 的端点级可观测性、交付失败回滚、意外错误指标、
query-string 拒绝回归。）

## 突变门（4/4 RED，还原后 GREEN）

- MA 恢复服务内广义静默 except（不计数直接 continue）→ T4+T9+T10 RED
  （更正要求 #4 的"no broad silent except can be restored without a
  mutation RED"直接证据）；
- MB 移除端点 SCAN_INCOMPLETE 日志+指标（仅回滚）→ T9 RED；
- MC 停用 used_at 单次使用校验 → T7 RED；
- MD 移除邮件失败分支的 rollback → T5 RED。

## 门禁

- GitNexus（编辑前，HEAD=93382cb2 重分析后查询）：impact
  `_enumerate_active_tenant_users` LOW（d1: request_reset/consume_reset，
  d2: forgot_password/reset_password——全部位于 allowlist 两文件内）；
  `forgot_password` LOW 0 受体；request_reset/consume_reset 图内无外部
  受体。提交后 re-analyze/status 钉住 HEAD。
- 聚焦回归（dc3b 全 16 + H2B-R1 10 + u6c + u6f + u6i6 + u6h2 + u6h3 +
  route authorization policy）：自然序 **107/107**、倒序 **107/107**。
- 两套独立全新完整后端栈（最终代码，fresh DB + alembic base→037 +
  Redis FLUSHALL；PG 用户 h2btester 以满足临时库安全门
  `MPANGO_ALLOW_TEMP_DB_CREATE=1` + `MPANGO_TEMP_DB_ALLOWED_PORTS`）：
  - Run A（h2b_r1_full_a_pg@15442 + h2b_r1_full_a_redis@6402）：
    **3683 passed / 2 failed / 48 skipped / 15 xfailed**（33:15）；
  - Run B（h2b_r1_full_b_pg@15443 + h2b_r1_full_b_redis@6403）：
    **3684 passed / 1 failed / 48 skipped / 15 xfailed**（33:40）；
  - xfail 节点集两跑 `diff` **完全一致**（15 节点）；skip 48=48；
    收集总数 3748 = R0 3746 + 本任务新增 2 测试；
  - 失败归因（均在 R1 变更 blast radius 之外，且已用 **R0 代码同栈复现**）：
    - `test_pw1r3_rate_limit_context.py::test_101st_anonymous_is_429…`
      两跑均失败、单测复现 3 次均失败，且在 **R0（pre-R1）代码 + 同样新栈**
      上同样失败——本机匿名路径 ~2s/请求 × 150 请求跨越多个 60s 固定
      窗口，计数永不达 100，无 429。属宿主时延环境问题，非 R1 回归；
      rate limiter 不在本任务 allowlist，不修。
    - `test_s5a_fresh_tenant_real_user_journey_gate.py` 仅 Run A 失败，
      Run B 通过；R1 代码与 R0 代码隔离运行均通过（库存 restock/deduction
      断言，与密码重置无交集）——非确定性干扰，非 R1 回归。
- py_compile（3 变更 .py）、`git diff --check` 干净、detect-secrets：
  3 文件原始扫描 0 发现、baseline 无新增、严格 UTF-8/无 BOM。

## 环境披露

- 全新任务栈：h2b_r1_pg16@15441 + h2b_r1_redis7@6401（聚焦/突变/RED 证明），
  `test_h2b_r1` fresh + alembic 037；两套全量栈如上（h2btester 用户 +
  临时库端口白名单；归因复现用 `test_h2b_r1_iso`）。
- venv：backend/.venv-h2b-r1 按冻结 requirements.txt 重建
  （bcrypt==4.0.1、asyncpg==0.31.0、SQLAlchemy==2.0.45 实测版本一致），
  另装测试专用 hypothesis（仅测试收集需要，不进产品依赖）。
- H1 历史触发不可追溯；本任务证明的是可复现漏洞类别 + 修复，不声称
  复现历史事故。
- 全量跑的 2/1 个失败均非 R1 所致（见上门禁归因；pw1r3 在 R0 代码上
  同栈同样失败）。R0 全量跑（3683/0）与本任务全量跑（A/B）的 passed
  基线一致：3683 = R0 口径；+2 为本任务新增测试。
