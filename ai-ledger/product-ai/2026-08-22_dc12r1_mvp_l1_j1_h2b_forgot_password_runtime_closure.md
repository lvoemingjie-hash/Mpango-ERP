# DC-12R1-MVP-L1-J1-H2-B-R0 — Forgot-Password Runtime Causal Diagnosis and Closure

- 日期：2026-08-22（+08:00）
- 执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-password-reset-runtime-closure-2026-08-22`
  （自冻结基线 `6e9470a1daa5d6eece29724316fdd8aef6b737c1` 创建）
- 裁决目标：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R0_MERGE_REVIEW`

## Phase 1 — 因果诊断（先复现，后修复）

### 环境与证明（五项独立）

任务栈（全新）：h2b_pg16@15438 + h2b_redis7@6398，fresh `test_h2b_r0`，
Alembic base→037；生产入口 `main:app`，MPANGO_ENV=staging（真实 JWT）；
任务自有 maildir（launcher 进程内 sink 落盘）。

1. **active 用户存在**：经官方生命周期（signup→verify→setup-credential→
   login）置备批发商后，直连 DB 断言其派生 tenant schema 中
   `is_active=true AND is_deleted=false` 的用户恰 1 条。
2. **真实 HTTP**：`POST /api/v1/auth/forgot-password` → 200 + 中性信封
   （`success:true, data:{}, message:"…not disclosed…"`）。
3. **token 前后计数**：0 → 1（真实发行，hash-only 行，tenant_id/schema
   NULL，used/revoked NULL）。
4. **邮件**：dev reset sink（`_DEV_RESET_EMAIL_DELIVERIES`）捕获 1 封，
   链接含 `resetToken=`（fragment-only）。launcher 首版仅转储 owner/
   retailer 两类 sink，重置邮件因此未落盘——补转储后确认。
5. **应用会话内异常路径**：扫描 `_enumerate_active_tenant_users` 全程
   `mark_session_as_system + run_as_system + ignore_tenant`；逐租户
   SAVEPOINT 隔离坏 schema。

### RLS/GUC 假设：**否证**（显式）

- 全部迁移（alembic/versions）**零 ROW LEVEL SECURITY 语句**——不存在
  RLS 策略可供会话上下文触发。
- 重置扫描显式 system-scope（三个显式绕过），且 fresh 栈真实 HTTP 下
  token 正常发行——若存在 GUC/租户过滤拦截，发行不可能成功。
- `password_reset_service.py` 在 H1 基线 `c5b66d26` 与本基线 `6e9470a1`
  的 git blob **字节一致**（`f99f32da…`）。

### 确证根因（与 H1 症状一致的可观测性缺陷）

`POST /auth/forgot-password` 的异常处理：
```
except EmailDeliveryNotConfiguredError: rollback
except Exception: rollback
```
——**吞掉全部内部失败且零结构化日志/零指标**。H1 的"三次提交中性 200 +
token 恒 0 + 无任何错误线索"正是该缺陷的表现：H1 环境中扫描/发行路径
的某次内部异常（具体触发数据已不可追溯）被静默回滚，外部只见中性 200
与"无 token、无日志"。

本基线健康数据下：
- 正常账户：token+邮件正常发行（0→1 实证）；
- 坏 schema（缺 users 表）：SAVEPOINT 隔离，**不毒化**后随健康租户；
- 非法 code wholesaler：get_tenant_schema 不抛（schema 由 UUID 派生），
  不毒化。
→ 旧缺陷（静默吞异常）不再可复现为"token 恒 0"，但**可观测性缺口本身
是真实缺陷**：内部失败对运维完全不可见（H1 无法定位根因即因此）。

## Phase 2 — 有界修复（allowlist 严格 5 文件）

- `backend/api/v1/auth.py`：forgot_password 异常分支增加**结构化内部
  观测**（外部信封保持完全中性）：
  - `EMAIL_DELIVERY_NOT_CONFIGURED` → `logger.error("password_reset.internal_failure",
    extra={event_class, phase, request_id})` + 指标
    `password_reset_internal_failures_total{event_class}`；
  - `UNEXPECTED` → 同事件类 + `exception_type`（**仅类型**；message/
    traceback 一概不记——SQL 错误可内嵌 tenant schema 名，违反
    "never log schema/credentials"）；
  - **绝不记录** email/token/password/hash/schema/凭据；
  - request_id 取自 request.state（request_logging 中间件注入）。
- `backend/core/prometheus_metrics.py`：新增内部失败计数器（唯一新增
  metric，事件类白名单 EMAIL_DELIVERY_NOT_CONFIGURED / UNEXPECTED）。
- `backend/tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py`
  （新）：8 测试（真实 ASGI+PG，见下）。
- 既有文件（`password_reset_service.py` 等）**零改动**；无迁移/模型/
  依赖/lockfile/部署/前端。

## 测试（新套件 8 项，真实 app+ASGI+PG）

- T1 旧代码 RED 复现：内部失败 → 中性 200 + 零 token；新代码结构化日志
  含 event_class=UNEXPECTED + request_id + exception_type（仅类型）；
  载荷绝不含 email/schema。
- T2 既有账户 GREEN：中性 200 + token +1 + 邮件 1。
- T3 不存在/非活跃：同形中性 + 零 token + 零邮件 + 零披露。
- T4 坏 schema 先行：健康租户 token 仍发行（无毒化回归）。
- T5 交付失败回滚：monkeypatch 服务内 `record_password_reset_email` 抛
  → 中性 200 + 零持久 token + 零邮件。
- T6 意外错误：中性外部 + 指标 +1 + 日志（T1 的度量侧）。
- T7 单次使用 + 跨租户一致性：重置一次生效、重放拒绝、两租户副本同新
  哈希（verify_password 双断言）。
- T8 query-string token 拒绝（秘密边界回归）。

## 突变门（3/3 RED，还原后 GREEN）

- M1 移除因果修复（except 分支去日志/指标）→ T1 RED。
- M2 抑制内部可观测性（去指标 inc）→ T6 RED。
- M3 允许邮件失败时提交 token（去 rollback）→ T5 RED。

## 门禁

- 聚焦回归（dc3b 全套 + 新 H2B + U6 credential/onboarding
  [u6c/u6f/u6i6/u6h2/u6h3] + route authorization policy）：
  自然序 105/105、倒序 105/105。
- 两套独立全新 PG16+Redis7 完整后端（最终 allowlist 合规代码，各 fresh
  DB + alembic 037 + FLUSHALL）：
  - Run A（h2b_full_a_pg@15439 + h2b_full_a_redis@6399）：
    **3683 passed / 0 failed / 0 errors / 48 skipped / 15 xfailed**；
  - Run B（h2b_full_b_pg@15440 + h2b_full_b_redis@6400）：
    **3683 passed / 0 failed / 0 errors / 48 skipped / 15 xfailed**；
  - xfail 节点集 `diff` **完全一致**（15 节点）；skip 数 48=48。
- py_compile、git diff --check、scoped pre-commit（含 detect-secrets，
  基线只读未改）、严格 UTF-8/无 BOM/mojibake 全过。
- GitNexus：impact（forgot_password LOW / request_reset LOW 1 直接 /
  _enumerate_active_tenant_users LOW 4 间接）编辑前已执行；提交后
  re-analyze/status 钉住 HEAD。

## 环境披露

- H1 原观测（真实 staging 历史数据）的触发数据已不可追溯；本任务以
  fresh 栈实证"健康数据正常发行 + 坏 schema 不毒化 + 可观测性缺口"，
  修复聚焦可观测性（外部信封零变化）。
- 运行期 venv 重建（H2B worktree 专属，按冻结 requirements.txt +
  bcrypt==4.0.1；主仓 venv 的 bcrypt 4.1+ 与产品不兼容）。
