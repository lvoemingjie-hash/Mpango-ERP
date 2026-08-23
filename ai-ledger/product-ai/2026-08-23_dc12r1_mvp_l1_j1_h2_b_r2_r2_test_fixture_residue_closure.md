# DC-12R1-MVP-L1-J1-H2-B-R2-R2 — 测试夹具残留闭合（FROZEN CHECKPOINT）

- 日期：2026-08-23（+08:00）
- 执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r2-test-fixture-residue-closure-2026-08-23`
  （自冻结候选 `34ccec116204b6a61b2e37c874b0c65953acfb43` 创建）
- 裁决目标：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R2_TEST_FIXTURE_MERGE_REVIEW`
- 因果证据（接受）：`8f63d1fbf5d40c6a30ce4ed606088da99f1e25db`（V2-R2，
  分类 TEST_FIXTURE_RESIDUE_DEFECT）
- 受保护基线（祖先核实）：`6e9470a1daa5d6eece29724316fdd8aef6b737c1`
- 范围：**恰 2 文件**（本台账 +
  `backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`）；
  无产品/迁移/模型/依赖/lockfile/配置/前端/部署变更。

## 0. 台账真值（不变声明）

- V2 无效环境（mpango/mpango）结论：**维持被取代状态**。
- V2-R1 Stack A 记账 **3682/5/48/15/0 保留**（非回归证据口径，非 zero-red）。
- **V2-R2 因果分类接受**：5 个 DC3B 失败由前置测试节点的数据库残留导致，
  候选产品代码无责。
- 产品 password-reset **fail-closed 行为零改动**：本任务未触碰任何产品文件；
  候选 `34ccec11` 的产品文件字节不变。
- 本任务**仅修复测试自有的数据库残留**（测试文件内 fixture/teardown）。
- **不声明** full-backend zero-red、浏览器 PASS 或合并批准——裁决链下一棒为
  Kilo 有界两文件源/测试审 → OpenCode WSL 双全新栈全量 zero-red →
  浏览器忘记/重置旅程 → CTO 受控合并。

## 1. 编辑前 GitNexus 上游影响（强制项）

- 基线索引（HEAD=34ccec11，up-to-date；CLI 1.6.9 因索引为 storage v42）：
  `impact test_service_cross_tenant_same_key_isolated --direction upstream
  --include-tests` → **direct=0 / processes_affected=0 / modules_affected=0，
  risk LOW（叶子测试节点，唯一调用方为 pytest 本身）**。
- 结论：无上游调用者/进程受体；改动爆炸半径限定在该测试文件内。

## 2. 因果实证扩展（相对 V2-R2 的重要更正）

V2-R2 将污染归因于单一残留（硬编码 `33333333-...` wholesaler +
`t_33333333333333333333333333333333` schema 无 users 表）。本任务在
**全新栈**上逐项复现，发现该节点实际提交了**两个**破坏 DC3B 扫描的
wholesaler 行：

| 实验（同一全新栈，逐项） | DC3B 结果 |
|---|---|
| DC3B 单独（干净对照） | **16/16 GREEN** |
| 目标节点运行后（两行残留：3333... 与 1111...） | **5 failed / 11 passed**（与 V2-R2 相同的 5 节点） |
| 仅手工清除 3333... 全部残留（保留 1111...） | **仍 5 failed** |
| 再清除 1111... 行 | **16/16 GREEN** |

- 第一残留：`33333333-3333-3333-3333-333333333333`（第二次
  `_seed_confirmed_order` 提交；`_bootstrap_minimal_tenant_schema` 建的
  schema 无 users 表）——与 V2-R2 一致。
- 第二残留：共享 t_test 租户 wholesaler `11111111-1111-1111-1111-111111111111`
  （第一次 `_seed_confirmed_order` 在节点内显式 `commit()` 提交；其派生
  schema `t_1111...` 在任何聚焦运行中都不存在）——**V2-R2 未覆盖**；
  在其全量运行 DB 中该 schema 可能由其他模块先行创建，故其
  "Failed-schema aggregate: 1" 观察与此不矛盾。
- 结论：teardown 必须拥有**本节点提交的两个租户的全部精确身份**，否则
  gate B（目标→DC3B 17/17）在全新栈上不可能为真。

## 3. 实现（授权文件 1：canonical payment service 测试）

新增（模块内、仅本节点使用）：

- 常量 `_SECOND_TENANT_ID` / `_SECOND_TENANT_SCHEMA`（固定 UUID/schema）；
- `_cross_tenant_residue_guard` fixture（依赖 `async_session`，故其 teardown
  先于 `async_session` 自身 teardown 运行）：
  - **捕获而非丢弃**：`second_retailer_id`（第二次 `_seed_confirmed_order`
    返回值）+ `first_tenant_id` / `first_retailer_id`（第一次调用的运行时
    精确身份，t_test 租户 UUID 不硬编码、从会话读取）；
  - **body 失败也运行**（fixture finalization），且不掩盖原失败：body 异常
    在 teardown 开始前已达 pytest；teardown 先幂等 rollback 测试会话
    （释放锁；`async_session` fixture 稍后重复同一 rollback）；
  - **全新会话/连接**（`AsyncSessionLocal()`，独立于测试事务）执行清理，
    FK 安全顺序：exact binding → exact retailer → exact wholesaler →
    `DROP SCHEMA ... CASCADE`；两租户分别按精确 UUID/精确对删除；
  - **禁止项遵守**：无软删、无前缀/LIKE/通配扫描、无全局重置、无
    DROP DATABASE；
  - **独立零残留证明**（第二条全新连接）：pg_namespace(schema)==0、
    public.wholesalers(3333...)==0、bindings(3333...)==0、
    retailers(captured second UUID)==0，另加 first-tenant 对应三项；
    任一非零 → teardown 断言失败（**fail-closed**，绝不静默通过）。
- 目标节点 body 断言/流程零改动（仅捕获写入 guard）——**gate A 行为不变**。

## 4. 测试真实性门禁（全部 GREEN；全新栈逐项重置后运行）

| 门 | 内容 | 结果 |
|---|---|---|
| A | 目标节点单独 | **1/1 GREEN** + 外部零残留证明 GREEN |
| B | 目标节点 → DC3B 全模块（自然序） | **17/17 GREEN** |
| C | DC3B 全模块 → 目标节点（倒序） | **17/17 GREEN** |
| D | canonical-payment 模块自然序 / 倒序 | **18/18 + 18/18 GREEN** |
| E | H2-B 套件；聚焦束 109（dc3b16+H2B12+u6c16+u6f7+u6i61+u6h214+u6h38+route35）自然/倒序 | **12/12；109/109 + 109/109 GREEN** |

倒序实现：`--collect-only -qq` 收集节点 ID 后按 CLI 逆序传入（pytest 保持
显式参数顺序；109 项倒序列表已核对）。

## 5. 突变门（全部按裁决 RED；还原后全部门 GREEN 重证）

| 突变 | 目标节点 | 零残留证明 | target→DC3B |
|---|---|---|---|
| M1 移除整个 teardown | **仍 PASS** | 外部证明 **RED**（4 项全残留：schema/wholesalers/bindings/retailer） | **复现 5 个 DC3B reds**（与基线同一组节点） |
| M2 仅删 wholesaler、保留 schema | teardown 断言 **ERROR（RED）**：schema=1、retailers=1 | 外部证明 **RED**（schema RESIDUE(1)） | DC3B 16/16（允许通过：无 wholesaler 行则扫描无访点） |
| M3 仅 DROP SCHEMA、保留 public 行 | teardown 断言 **ERROR（RED）**：wholesalers=1、bindings=1、retailers=1 | 外部证明 **RED**（wholesalers/bindings/retailer 全残留） | —（门未要求） |

还原候选后复跑：A（1/1+证明 GREEN）、B 17/17、C 17/17、D 18/18×2、
H2B 12/12、聚焦 109/109 自然+倒序——**全部 GREEN**。

## 6. 质量门禁

- `py_compile`：OK；`git diff --check`：干净。
- scoped pre-commit（trailing-whitespace / EOF / large-files /
  **detect-secrets** 对变更文件）：全部 **Passed**；`.secrets.baseline`
  前后字节不变（sha256 前 16 位一致）。
- detect-secrets 原始扫描变更测试文件：**0 发现**。
- 严格 UTF-8 / 无 BOM：OK。
- GitNexus：提交前 `detect_changes`（MCP `detect_changes`，repo=Mpango-ERP，
  scope=working）→ **6 个变更符号全部位于该测试文件、affected_processes=[]、
  risk=low**；提交后 re-analyze + status 钉住新 HEAD。
- 范围钉住：提交恰 2 文件；候选产品文件与 `34ccec11` 字节一致
  （`git diff 34ccec11 HEAD -- <产品路径>` 为空）。

## 7. 环境披露

- 任务自有栈：`h2b_r2r2_pg16`@15441（h2btester/test_h2b_r2r2，fresh +
  alembic 037）+ `h2b_r2r2_redis7`@6401；每实验门之间 DROP/CREATE
  DATABASE + alembic 重置（重置脚本为任务自有未跟踪辅助文件，已随收尾
  删除，不入库）。
- venv：`backend/.venv-h2b-r2r2` 按冻结 requirements.txt 重建
  （bcrypt==4.0.1 / asyncpg==0.31.0 / SQLAlchemy==2.0.45 实测一致）；
  测试专用：pytest 9.1.1 + **pytest-asyncio 1.4.0**（pytest.ini 的
  `asyncio_default_*_loop_scope` 需 ≥0.24 语义；0.21.2 会导致会话级
  fixture/loop 跨接错误——环境事实，非产品问题）+ hypothesis。
- 本 Windows 宿主不执行全量后端栈（裁决要求不变）。

## 8. 后续（不变）

Zcode 冻结检查点（本分支，推送后 STOP）→ Kilo 有界两文件源/测试审 →
OpenCode WSL 双全新栈全量 zero-red → 浏览器忘记/重置旅程 → CTO 受控合并。
