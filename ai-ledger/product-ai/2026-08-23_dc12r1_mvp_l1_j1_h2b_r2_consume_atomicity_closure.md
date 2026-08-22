# DC-12R1-MVP-L1-J1-H2-B-R2 — 消费级多租户原子性闭合（STOP_AND_REPORT）

- 日期：2026-08-23（+08:00）
- 执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-consume-atomicity-closure-2026-08-23`
  （自 R1 提交 `fc2db4fe2254f91a203c27cca2bcb4cd61c810a1` 创建）
- 裁决目标：`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_INDEPENDENT_ZERO_RED`
  ——本分支仅作为**证据检查点**推送，**不声明 merge-ready**。

## 0. R1 裁决状态：被本 R2 取代（superseded）

- R1（fc2db4fe）完成了**请求级**扫描闭合（见下节区分），但其
  `consume_reset` 仍保留 R0 遗留的**尽力而为扇出**：逐副本
  SAVEPOINT `except: continue` 吞掉单副本更新失败、部分扫描时仍更新
  可达副本并标记 token 已用。这允许同一 email 的租户副本出现
  **分叉的密码哈希**——正是规范多租户同哈希规则所要保护的不变量。
- **R1 全量门禁的性质更正**：R1 台账中两套全量栈（A 3683/2、
  B 3684/1）是**非回归证据**（失败在 R0 代码同栈同样失败，已归因），
  **不是 zero-red PASS**。本 Windows 宿主存在 pw1r3 环境性失败
  （匿名路径 ~2s/请求 × 60s 固定窗口），zero-red 全量门必须在独立
  低负载 Lubuntu 栈上执行——这是本裁决 STOP_AND_REPORT 的直接原因。
- 合并前置链（R2 后）：Kilo 有界源审 → 独立低负载/Lubuntu 全量
  zero-red → 浏览器忘记/重置旅程 → CTO 合并决定。

## 1. 两阶段闭合的区分（请求级 vs 消费级）

| 阶段 | 闭合轮 | 契约 |
|---|---|---|
| 请求级（POST /auth/forgot-password） | R0（端点可观测）+ R1（扫描级） | 扫描失败绝不静默转为"账户不存在"；中性 200 外封不变；恰 1 次内部事件（SCAN_INCOMPLETE / SCAN_PARTIAL）；R1 全部保留，本轮零改动请求路径语义 |
| 消费级（POST /auth/reset-password） | **R2（本轮）** | 任何 `failed_schema_count>0` 在**任何密码更新之前**失败关闭（无论 copies 是否为空）；扇出**全有或全无**：每个发现副本必须恰好更新 1 行（rowcount 校验）；任何校验/更新失败抛脱敏类型错误；端点回滚外部事务（撤销所有已暂存副本更新）；token 保持未用/可重试；**无尽力而为路径** |

## Phase 1 — 可复现缺陷（消费级）的真 PostgreSQL 证明

- R1 代码（fc2db4fe）上运行新测试：**T11/T12 双 RED**——部分扫描时
  R1 返回 200 并更新可达副本、token 被标记已用；触发器强制单副本
  UPDATE 失败时 R1 吞错继续、同样 200+已用。即：部分应用与 token
  误消费在 R1 上确定性发生。
- R2 代码：12/12 GREEN（连跑两次，无跨测试干扰）。

## Phase 2 — 有界修复（allowlist 严格 4 文件；prometheus_metrics.py 零改动）

1. `backend/services/password_reset_service.py`
   - 新增 `PasswordResetApplyFailedError`（构造即脱敏：仅
     updated_count / remaining_copy_count 两个整数；不链入原始异常）；
   - `consume_reset`：`scan.failed_schema_count > 0` → 无条件在扇出前
     抛 `PasswordResetScanIncompleteError`（R1 的 copies 非空放行
     分支删除）；
   - 扇出循环：`validate_identifier` 失败 → 抛类型错误；每副本
     `UPDATE` 后校验 `rowcount == 1`，否则抛类型错误；**移除逐副本
     SAVEPOINT 与 except:continue**（失败必须中止整个消费，不再隔离
     跳过）；`used_at` 仅在全部副本成功后写入；
   - `_enumerate_active_tenant_users` 与 `request_reset`（请求级 R1
     语义）**零改动**。
2. `backend/api/v1/auth.py`
   - `reset_password` 新增 `PASSWORD_RESET_APPLY_FAILED` 分支（第 5 个
     固定事件类）：恰一次结构化日志（event_class/phase/request_id/
     updated_count/remaining_copy_count——仅计数）+ 指标 +1 + 外部
     事务回滚 + **既有中性 401 INVALID 信封**（公开形状零变化）；
   - 扫描失败分支（reset_consume_scan）与请求级分支保持 R1 语义。
3. `backend/tests/test_dc12r1_j1_h2b_forgot_password_runtime_closure.py`
   （10 → 12 测试）
   - **T11（部分扫描）**：同 email 两租户副本，改任一已提交 users
     表名（行证据保留在改名表中），另一副本可达 → 重置中性 401、
     恰 1 次 SCAN_INCOMPLETE 事件+指标、**两副本哈希均仍为旧密码**
     （可达副本不被部分更新）、`used_at` 为 NULL；恢复表名后**同一
     token** 恰一次重置两副本（重放 401）。
   - **T12（部分应用）**：两副本均可扫描；在第二副本安装真实 PG
     `BEFORE UPDATE` 触发器强制 UPDATE 失败 → 重置失败关闭、恰 1 次
     APPLY_FAILED 事件+指标（updated_count=1, remaining=1）、**第一
     副本的暂存更新被外部回滚**（两副本均保持旧密码）、token 未用；
     删除触发器后**同一 token** 重置两副本。
   - 修复 R1-T10 遗留的会话卫生缺陷：上下文关闭后的 `db2` 使用会
     开启悬挂事务，其 AccessShare 锁使下一测试 fixture 的
     `DROP SCHEMA CASCADE` 命令超时（T11 首轮 setup ERROR 的根因）；
     改用自管理会话的 `_copy_password_hash`。
4. `ai-ledger/product-ai/2026-08-23_dc12r1_mvp_l1_j1_h2b_r2_consume_atomicity_closure.md`
   （本台账）。

## 突变门（3/3 RED，还原后 GREEN）

- C1 恢复 `if not copies`-only 守卫（扫描失败仅在 copies 为空时失败
  关闭）→ **T11 RED**；
- C2 恢复逐副本 `except: continue`（尽力而为 + rowcount 不中止）→
  **T12 RED**；
- C3 部分失败仍消费 token → **T12 RED**（token-actionability 断言）。
  实现说明：仅把 used 标记移到扇出前会被端点回滚抵消（无害突变），
  诚实的回归形态是**标记并提交**后继续——以此形态验证 RED。

## 门禁

- 聚焦回归（dc3b 全 16 + H2B 12 + u6c + u6f + u6i6 + u6h2 + u6h3 +
  route authorization policy）：自然序 **109/109**、倒序 **109/109**；
  H2B 套件连跑两次 12/12（无跨测试干扰回归）。
- 突变 C1/C2/C3 全 RED；还原后 12/12 GREEN。
- **本 Windows 宿主不执行全量后端栈**（裁决要求）：zero-red 全量门
  移交独立低负载/Lubuntu 栈执行（R1 台账已记录本机 pw1r3 环境性
  失败及 pre-R1 归因证据）。
- py_compile（3 变更 .py）、`git diff --check`、scoped pre-commit
  （含 detect-secrets，`.secrets.baseline` 字节不变）、detect-secrets
  原始扫描 0 发现、严格 UTF-8/无 BOM。
- GitNexus：impact 编辑前已执行（consume_reset/reset_password 无外部
  受体；_enumerate 2 直接 + 2 间接受体全部位于 allowlist 两文件）；
  detect_changes 提交前；提交后 re-analyze/status 钉住 R2 HEAD。

## 环境披露

- 聚焦/突变复用 h2b_r1_pg16@15441 + h2b_r1_redis7@6401（alembic 037）；
  venv 按 R1 台账配方重建（bcrypt==4.0.1 / asyncpg==0.31.0 /
  SQLAlchemy==2.0.45 实测一致）。
- 收尾清理：仅删除 6 个任务自有容器
  （h2b_r1_pg16 / h2b_r1_redis7 / h2b_r1_full_a_pg /
  h2b_r1_full_a_redis / h2b_r1_full_b_pg / h2b_r1_full_b_redis），
  验证 15441–15443 与 6401–6403 端口释放；宿主自有容器未触碰。
- 无迁移/模型/依赖/lockfile/部署/前端变更；无 pricing/barcode/
  deployment/human journey。
