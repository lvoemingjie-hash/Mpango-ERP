# DC-12R1-MVP-L1-J1-H2-B-R2-R3 — 全量套件确定性测试卫生闭合（STOP_AND_REPORT）

- 日期：2026-08-23（+08:00）；执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-full-suite-test-hygiene-closure-2026-08-23`
  （自父提交 `683297f4471675657f2d85c8eccc42858c886754` 创建；
  `git fetch --all --prune` 后核实 parent/remote/baseline/report 四引用）
- 受保护基线（祖先核实）：`6e9470a1daa5d6eece29724316fdd8aef6b737c1`
- 已接受的历史 STOP 证据 `b4a6e167da6bc203b8b844c1ed05b8e7469ef5cc`
  **原样保留**（零改动）。
- 实施后裁决：`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_INDEPENDENT_ZERO_RED`
- 范围：**恰 5 文件**（4 个测试模块 + 本台账）；无产品/服务/模型/迁移/
  依赖/配置/前端变更；`LocalJobQueue`、password-reset 生产代码、
  `_seed_confirmed_order` 零触碰。

## 1. Phase 1 — 证明与影响

### 1.1 编辑前 GitNexus impact（target_uid 消歧，upstream）

| 符号 | direct | procs | risk |
|---|---|---|---|
| s4 `test_job_metrics` | 0 | 0 | LOW |
| s5d4b `test_route_settlement_failure_rolls_back…` | 0 | 0 | LOW |
| pw1r4 `_seed_tenant_readiness` | 0 | 0 | LOW |
| pw1r4 `_setup_two_tenants` | 5 | 0 | **MEDIUM**（披露：仅新增 registry 追加，签名/语义零变化） |
| pw1r4 `two_tenants` fixture | 0 | 0 | LOW |
| u6i2 `_insert_registration` | 7 | 0 | **MEDIUM**（披露：仅新增 registry 追加，签名/返回值零变化） |
| u6i2 `_u6i2_public_schema` / `_clear_u6i2_rows` | 0/1 | 0 | LOW |

无 HIGH/CRITICAL → 无需 STOP。（参考：`_seed_confirmed_order` 仍为
CRITICAL/30 直接调用者——继续零触碰。）

### 1.2 提交节点普查（全新库逐模块实测）

| 模块 | 残留（模块运行后） |
|---|---|
| s5d4b（12 节点） | 共享 1111... wholesaler active + 1 binding + 1 retailer（唯一提交节点：route_settlement_failure…） |
| pw1r4（9 节点） | **4 个**随机 wholesaler（fixture 2 + forced-failure before_ddl_engine 2）各 +binding/retailer；t_r4a_* schema 已被既有清理清零，但 public 行全部存留 |
| u6i2（14 节点） | **1 个孤儿 wholesaler**（`with_wholesaler_id=False` 参数化分支：wholesaler 恒创建，而 `_clear_u6i2_rows` 经 registration 邮箱反查无法定位）；派生 schema 未创建 |
| s4（11 节点） | 无 DB 残留（仅指标时序问题） |

未发现授权范围外的其他污染模块 → 无需 scope-widening STOP。

## 2. Phase 2 — 确定性作业指标（test_job_metrics 仅此节点）

- 移除两个固定 `sleep(0.3)`：改为 **handler 内 Event 停靠**（release 前
  指标可证为 0）+ `asyncio.wait_for(queue.queue.join(), 10s)` 有界完成
  等待（join 仅在成功与失败作业都 task_done 后返回）。
- 失败作业 `max_retries=0`（原默认 3 次重试的时序依赖消除）。
- 断言保持 completed ≥ 1 且 failed ≥ 1；无轮询 sleep/放大 sleep/重试/
  条件化断言。其余 s4 节点零改动。

## 3. Phase 3 — 精确夹具所有权（fail-closed finally 清理）

- **s5d4b**：唯一提交节点挂 `_shared_tenant_guard`——测试前快照共享
  1111... public 全行（复用 DC11D R2-R2-R1 助手），测试后先 rollback
  body 会话，再以全新连接精确恢复（预置行绝不删除；任务新建行清除；
  绑定他者的 retailer 受保护），第三条全新连接证明 post == pre。
- **pw1r4**：`_seed_tenant_readiness`/`_setup_two_tenants` 将精确身份
  （wholesaler/retailer id、schema 名、派生 schema 名）登记入模块级
  registry；模块级 autouse guard 在 finally 中以**全新引擎**按 FK 安全
  序（binding → retailer（无他者绑定才删）→ wholesaler → 精确 schema
  DROP IF EXISTS）清理，并独立证明 pg_namespace/public 计数全零；错误
  收集为 BaseExceptionGroup，不掩盖原测试失败。
- **u6i2**：`_insert_registration` 登记 wholesaler id；模块级 autouse
  guard finally 清理精确 wholesaler/binding/派生 schema 并独立证明零残留。
- 全部遵守：无 LIKE/前缀/通配/全局重置/软删-only/DROP DATABASE。

## 4. Phase 4 — 真实性门禁（全部 GREEN；关键实验前重置库）

| 门 | 结果 |
|---|---|
| s4 自然/倒序 | 11/11 + 11/11 |
| test_job_metrics 重复 | **50/50**（50 个独立 pytest 进程，单次 ~0.8s，无 sleep） |
| 三 producer 模块自然/倒序 | 12/12、9/9、14/14（两种顺序） |
| producers → DC3B | producers 35/35 → **DC3B 16/16**；束后 scan-breaking active wholesalers = **0** |
| DC3B → producers | **DC3B 16/16** → producers 35/35 |
| 共享 1111 post == pre | 预置 suspended/777.77/固定 binding id 状态经三 producer 后 JSON **逐字节一致** |

### 突变门（全部按裁决 RED；还原后复跑 GREEN）

| 突变 | 结果 |
|---|---|
| M1 移除作业完成等待 | **3/3 次确定性 RED**（`assert 0 >= 1`；有界 ~30s） |
| M2 抑制精确 schema 清理（pw1r4 fixture+guard 双处） | 模块 teardown **ERROR：残留证明 RED**（pg_namespace 非零） |
| M3 抑制 public 行恢复（s5d4b） | teardown **ERROR：ownership violation 快照证明 RED** |
| M4 抑制 u6i2 guard | u6i2 仍 14/14（不掩盖）→ 孤儿 wholesaler 存留 → **DC3B 5 red** |

## 5. Phase 5 — 回归门禁

- 前驱束（DC11D→canonical→DC3B）自然 **44/44**、倒序 **44/44**。
- H2-B **12/12**；聚焦束恰 109 项：自然 **109/109**、倒序 **109/109**。
- **两套独立全新 PG16+Redis7 全量套件（每栈恰一次权威运行，无失败重跑充数）**：
  - 环境披露（重要）：首跑 Stack A 出现 1 失败 = pw1r3
    `test_101st_anonymous_is_429…`。根因（实测定位，非代码回归）：该模块
    使用**任务专属 Redis**（默认 `redis://127.0.0.1:26379/15`，本机无监听），
    autouse fixture 换入的 limiter 每请求连接停滞 ~2s → 150 匿名请求跨越
    多个 60s 固定窗口，计数永不达 100。模块自带官方环境开关
    `PW1R3_TEST_REDIS_URL` 指向任务 Redis（localhost:6401/15）后单测
    **4 秒 GREEN**。纯环境配置修复，零文件改动。修正后两栈重跑：
  - **Stack A**（h2b_r2r3_pg16@15441 + redis@6401，fresh + alembic 037）：
    **3687 passed / 0 failed / 0 errors / 48 skipped / 15 xfailed / 0 xpassed**
    （22:00）；skip 48 节点集与 xfail 15 节点+原因集已导出。
  - **Stack B**（h2b_r2r3b_pg16@15442 + redis@6402，fresh + alembic 037）：
    **3687 passed / 0 failed / 0 errors / 48 skipped / 15 xfailed / 0 xpassed**
    （21:08）。
  - 两栈 skip/xfail 节点+原因集 `diff` **完全一致**；计数对账
    gap=0（3687+48+15=3750 两栈相同）。

## 6. Phase 6 — 质量与交付

- py_compile（4 变更 .py）、`git diff --check`、严格 UTF-8/无 BOM：OK。
- scoped pre-commit（含 detect-secrets）全 Passed；`.secrets.baseline`
  字节不变；4 文件原始扫描 **0 发现**。
- GitNexus：提交前 `detect_changes`（MCP）→ changed backend files = **恰
  4 个授权测试文件**、affected_processes=[]、risk low；提交后
  re-analyze（--force）+ status 钉住新 HEAD。
- 最终 delta 恰 5 文件；推送隔离源分支并证明 local == remote。
- 收尾清理：任务自有容器/端口/辅助脚本全清；b4a6e167 原样保留。

## 7. 后续（裁决链不变）

Kilo 有界五文件审 → OpenCode WSL 双全新栈字面 zero-red 复跑 →
浏览器忘记/重置旅程 → CTO 合并决定。
