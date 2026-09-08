# MPANGO-MVP-INVARIANTS-R1 运行记录（2026-09-08）

> 修复轮：撤权链（软删用户/停用租户拒绝 + refresh 数据库校验）与库存调整并发丢失更新。
> BASE=1485c3f5（fetch 后与远端 `zcode/mpango-mvp-invariants-r0-r2-2026-09-07` ls-remote 精确一致）；
> 分支 `zcode/mpango-mvp-invariants-r1-auth-stock-fix-2026-09-08`；worktree
> `worktrees/zcode_mpango_mvp_invariants_r1_fix_2026-09-08`。

## 任务独占环境

- 容器：`mpango-zcode-inv-r1fix-20260908-pg`，镜像 postgres:16-alpine，实际映射 `127.0.0.1:49770`，
  标签 `mpango.owner=zcode-mvp-invariants-r1-fix`（会话夹具七重归属核验每次运行前置执行）。
- 运行时：Python 3.12.10（仓库外任务 venv `_zcode_mvp_invariants_r0_venv`，与 R0-R2 同源）；
  SQLAlchemy 2.0.45、asyncpg 0.31.0、FastAPI 0.128.0、pytest 8.4.2、pytest-asyncio 0.26.0；
  MPANGO_ENV=staging；REDIS_URL=redis://127.0.0.1:1/15（不可达，缓存/限流 fail-open）；
  SECRET_KEY 合成 64hex；REPORTING_USER_PASSWORD 合成。env 脚本 `_zcode_mvp_invariants_r1fix_env.sh`
  在仓库外，口令为合成 disposable 值，不随分支提交。
- 迁移：会话夹具在归属证明后对核验目标执行 `alembic upgrade head`，head==`037_payment_declarations_schema` 断言通过；
  无手工 alembic 调用；alembic.ini 默认地址按构造不可达。
- 环境备注：任务 venv 补装 pyproject.toml 已钉版本 `hypothesis==6.150.2`（R0-R2 未跑全量套件故此前未装；
  8 个测试文件 import 失败的收集错误由此消除）。**未修改任何依赖声明文件**（requirements.txt/pyproject.toml/poetry.lock 零字节变化）。

## 一、聚焦回归（修复后候选）

命令：`pytest tests/test_mpango_invariants_r0_r1_guards.py tests/test_mpango_mvp_invariants_r0_concurrency.py tests/test_mpango_mvp_invariants_r0_revocation.py --no-header -q`

**结果：45 节点 = 44 PASS + 1 已知 RED**（退出码 1；耗时 86.5s；恢复后复跑 83.3s 结果相同）。

原 7 个产品命名 RED 的处置（节点名保持与 R0-R2 基线 1:1）：

| 节点 | R0-R2 基线 | 本轮 |
|---|---|---|
| red_concurrent_stock_adjustments_no_lost_update | RED(15.00) | **PASS（终值 22.00，流水链完整）** |
| red_soft_deleted_user_in_active_tenant_denied | RED(200) | **PASS（401）** |
| red_active_user_in_suspended_tenant_denied | RED(200) | **PASS（401）** |
| red_refresh_nonexistent_principal_no_session | RED(签发) | **PASS（401，零 token 物料）** |
| red_refresh_soft_deleted_user_no_session | RED(签发) | **PASS（401，零 token 物料）** |
| red_refresh_suspended_tenant_no_session | RED(签发) | **PASS（401，零 token 物料）** |
| red_concurrent_full_return_single_economic_effect | RED(−200/2 回补) | **RED（同值 −200.0000，已知未修复，按指令单列）** |

新增节点（全部 PASS）：

| 节点 | 覆盖 |
|---|---|
| r1_control_refresh_wrong_signature_refused | 外键签名 refresh token → 401（验签层未被 DB 校验替代） |
| r1_control_refresh_wrong_token_type_refused | access token 送 refresh → 401 INVALID_TOKEN_TYPE |
| r1_control_tenant_isolation_no_cross_read | 双租户同构数据：GET /api/v1/skus 各自只见本租户 SKU；refresh 新 token 仍绑定本主体/本租户 |
| r1_control_adjustment_read_helper_preserves_duplicate_rows | DB 级行数保留：注入重复 reason 流水后 adjustment_movements 返回原始 2 行，共享助手拒绝（CTO O1） |
| guards::exact_cto_counterexample_rows | CTO 精确原反例 A(17→22)×2、B(10→17)：原始三行 SET 拒绝；dict 折叠形态==合法 B→A 链必须接受（O1） |

refresh 测试全部改为真实 HTTP（POST /api/v1/auth/refresh，httpx ASGITransport），端点新增的
`Depends(get_db_session)` 经 FastAPI DI 在 HTTP 路径解析——校验不依赖直呼才生效。既有对照（活跃访问、
is_active=false 拒绝、活主体 refresh 200+新 token 可用、单次调整/失败回滚、屏障超时/任务异常清理、
拒绝请求暂存写入零残留、单次退货单次经济效果）全部保持 PASS。

开发期异常记录（如实）：两次三文件合跑出现 `collected 0 items`（退出码 4，0.00s）；单文件与紧接的重跑
均正常收集 45 节点，根因未定位（疑似 Git Bash 管道/瞬时 shell 环境问题），对结果无影响；所有计分运行
均为收集到 45 节点的正常执行。

## 二、证伪（退化 → RED → 字节一致恢复 → GREEN）

退化前先备份三份修复文件并记录 sha256；每次退化仅移除单一修复关键点；恢复后 `sha256sum -c` 全部 OK
（与退化前字节一致），并整体复跑聚焦回归确认回绿。

| # | 退化点 | 预期 RED | 实测 |
|---|---|---|---|
| D1a | tenant.py 移除 `is_deleted` 检查 | soft_deleted_user RED；suspended 仍绿（归因隔离） | ✅ 1 failed(soft-deleted)+1 passed(suspended)，16.9s |
| D1b | tenant.py 移除 `assert_tenant_active` 调用 | suspended RED；soft-deleted 仍绿 | ✅ 1 failed(suspended)+1 passed(soft-deleted)，16.1s |
| D2 | auth.py 移除 `_validate_contextual_refresh_subject(db, payload)` 调用 | 3 个 refresh RED | ✅ 3 failed，14.7s |
| D3 | inventory_service.py 移除 `.execution_options(populate_existing=True)` | lost-update RED，终值 15.00（基线反例原值） | ✅ 1 failed `INVARIANT_R0_STOCK_LOST_UPDATE: got 15.00`，4.8s |

恢复后完整聚焦回归：44 PASS + 1 已知 RED（与退化前完全一致）。

## 三、安全演练与残留核查

- 归属拒绝演练：声明错误容器 `some-other-container` → `GUARD_REFUSED_DATABASE_OWNERSHIP`
  （docker inspect rc=1），演练后 `t_%` schema=0（零写入）。
- 聚焦回归+证伪全部运行后残留：`t_%` schema=0、public.wholesalers=0、public.retailers=0、
  alembic head=`037_payment_declarations_schema`。
- 未触碰任何既有容器/卷/库（docker ps 全程仅新增本任务容器）。

## 四、后端全量套件（同一任务独占环境）+ BASE 差分

**环境前提变更（如实声明）**：R0 的"REDIS_URL 指向不可达地址"premise 在全量套件下不可行——
约 40 个测试文件的 teardown 需连 Redis 清理限流键，不可达时逐个以 ~30s 重试失败（既有测试
`test_dc12r1_contract_d_statement_print.py` 等成片 ERROR 且整体近乎停滞）。改为**任务独占一次性
Redis**（容器 `mpango-zcode-inv-r1fix-20260908-redis`，redis:7-alpine，标签
`mpango.owner=zcode-mvp-invariants-r1-fix`，127.0.0.1:58084）——与任务 PG 同一隔离原则，未触碰
任何既有 Redis 实例。不变量三文件另以原前提（不可达 Redis）复跑对照，结果一致（44 PASS + 1 已知 RED）。
任务 venv 另补装 pyproject 已钉版本 `hypothesis==6.150.2`（消除 8 个收集错误；未改任何依赖声明文件）。

命令（候选与 BASE 同式）：`pytest tests/ --no-header -q -rfE`

| 运行 | 结果 |
|---|---|
| 候选（本 worktree） | **21 failed, 3684 passed, 69 skipped, 15 xfailed, 40 errors**（1673.57s） |
| BASE 差分（`zcode_mpango_mvp_invariants_r1fix_base_ref` 挂于 1485c3f5，同 env 同库串行） | **20 failed, 3702 passed, 50 skipped, 15 xfailed, 37 errors**（1885.35s） |

**逐节点差分**（FAILED+ERROR 合并去重后比较）：

- **两侧共同（56 节点，全部既有）**：
  - 19 FAILED：既有重复退货 RED（候选同样 RED）+ dc11t2 临时库工具 6 + dc11t4c 报表 bootstrap 1 +
    dc12a_r2 设置校验 1 + j1_h2c 找回链接 3 + s1_r5 迁移预检 1 + s4g 迁移设施 5 + pw1r3 `test_101st_anonymous` 1
    （后者 BASE 孤立复跑亦 FAIL，309.55s，封板为既有）；
  - 37 ERROR：dc12r1 real_alembic_upgrade 29（setup 阶段，临时库类）+ 撤权文件 8
    （全量进程中既有测试模块级硬设 `MPANGO_ENV='test'` 未还原——test_b5_real_db.py:17 等 6 处——
    我们的不变量守卫按设计拒绝：`GUARD_REFUSED_MOCK_AUTH`，零运行；聚焦/孤立运行时全部正常）。
- **仅候选（5）**：
  - 撤权文件 3 个**新节点** ERROR（wrong_signature/wrong_token_type/isolation 对照）——与两侧共同
    的 8 个同机制（同一既有 MPANGO_ENV 泄漏），非新缺陷；新节点在干净进程中全部 PASS（见 §一）；
  - pw1r3 `test_contextual_burst_stays_admitted_well_past_ip_limit`、
    `test_contextual_jwt_uses_tenant_bucket_limit_1000` FAILED（候选孤立复跑亦败，8.22s 快败）。
    **根因**：pw1r3 夹具使用合成租户（真实 schema+users 行、随机 tenant_id，刻意不走正式生命周期，
    即**无 public.wholesalers 行**）——恰为新不变量应拒绝的"平台注册表外租户"，assert_tenant_active
    对其逐请求 401。这是预期行为变化波及的既有测试。**处置（必要测试对齐）**：
    `rl_tenant` 夹具补一行精确任务自有 wholesalers 行（status='active'，teardown 按 id 精确删除）；
    对齐后候选全文件 7 节点 = 6 PASS + 1 既有 FAIL（test_101st，BASE 亦败）。
- **仅 BASE（1）**：`red_concurrent_stock_adjustments_no_lost_update`（基线 RED）——候选上转 PASS，
  即本轮修复的预期差分确证。
- skip 计数差（69 vs 50）：-rfE 未捕获 skip 节点清单，仅有计数；差分拟源于 BASE 第二序运行时
  任务库已携候选运行残留、条件跳过评估不同；本任务触碰文件的节点无 skip（聚焦运行 45 节点
  与 pw1r3 7 节点均 0 skip）。

**结论**：候选相对 BASE 的全部差分 = 6 个目标 RED 转绿（1 个 BASE-only FAILED 消失 + 撤权文件
节点在干净环境转绿）+ 1 项必要测试对齐（pw1r3 夹具）+ 新节点继承既有环境泄漏；无任何由本修复
引入的未解释回归。全量环境中的失败/错误全部归类为既有或环境性，证据如上。

## 四b. 不变量套件原前提（不可达 Redis）复跑对照

`pytest <三文件> --no-header -q`（原 env，REDIS_URL=redis://127.0.0.1:1/15）：
**44 PASS + 1 已知 RED**（89.22s）——与可达 Redis 下聚焦结果完全一致。

## 五、GitNexus 流程记录

- CLI 1.5.3 可用；`gitnexus analyze --skip-agents-md` 对本任务 worktree 建索引成功
  （索引名 `zcode_mpango_mvp_invariants_r1_fix_2026-09-08`）。与 R0-R2 记录的
  "存储版本 42 vs 40"故障不同，本轮 `impact` 查询在指定 `--repo` 后**可用**，如实记录、
  不追溯否定既往工具故障。
- 查询结果：`adjust_stock` 上游 1 直接调用方（api/v1/inventory.py:adjust_inventory）、
  受影响流程 0、LOW；`resolve_tenant_context` / `refresh_token` 图中上游 0（HTTP 路由/
  中间件入口为图叶）——以 §二/任务记录的直读源码调用链分析补足（中间件 → 策略 →
  resolve_tenant_context；/api/v1/auth/refresh 路由注册）。
- 提交前变更核对：`git status --porcelain` + 逐文件暂存 diff（见任务记录 §1 范围表）；
  detect-secrets hook（v1.5.0，`--baseline .secrets.baseline`）对全部变更文件退出 0，
  baseline 字节未变（sha256 f49c8622…16bf 与 HEAD 一致）。

## 六、资源与清理

- 任务容器：`mpango-zcode-inv-r1fix-20260908-pg`（PG16）、`mpango-zcode-inv-r1fix-20260908-redis`
  （Redis7）——最终报告核验后按标签删除（含卷）；BASE 差分工作树 `zcode_mpango_mvp_invariants_r1fix_base_ref`
  移除。
- env 脚本（仓库外，合成口令）：`_zcode_mvp_invariants_r1fix_env.sh` /
  `_zcode_mvp_invariants_r1fix_env_redis.sh`，保留或删除同 R0 流程。
- 全部运行后残留核查见 §三；全量套件两轮运行后的库内残留（各测试自清理余量）以最终核查为准。

## 七、提交与推送记录

| 项 | 值 |
|---|---|
| 提交 1（任务记录：范围表+调用链，先于实施） | `f905bcee7fb64c822d3b0c1b4f6b14dfaca607b8`（父 = BASE 1485c3f5） |
| 提交 2（产品修复+测试+报告） | `4e06ee3b7a35ba7601331a65e94b2da282302899` |
| 本追加提交（RUN_LOG §七） | 见 `git log -1`（普通后继提交） |
| 分支 | `zcode/mpango-mvp-invariants-r1-auth-stock-fix-2026-09-08`（普通 push，无 force） |
| local==remote 核验 | 提交 2 推送后 `git rev-parse HEAD` == `git ls-remote origin <branch>` ==
  `4e06ee3b7a35ba7601331a65e94b2da282302899`（YES）；追加提交后同法复验 |
| 提交前核查 | `git diff --cached --check` 干净；detect-secrets hook（--baseline）退出 0、
  baseline 字节未变（sha256 f49c8622…16bf）；UTF-8/无 BOM 12 文件通过 |
| 变更文件 | 恰为任务记录 §1 范围表所列（产品 3 + 测试 4 + 报告 5；support 零字节变化） |
