# DC-12R1-MVP-L1-J1-H2-B-R3-R2-V2 — LUBUNTU Independent Fresh-Runtime Authoritative Backend Final

- **日期:** 2026-08-26（+08:00）
- **执行方:** OpenCode — Lubuntu 原生独立主机
- **风险等级:** V3_MERGE_CRITICAL；CHANGE_CLASS: AUTH_TENANT_ISOLATION_GLOBAL_TEST_STATE
- **CLAIM_CEILING:** INDEPENDENT_BACKEND_GATE_PASS（非 browser PASS、非 merge/release approval）
- **模式:** 单次 fresh-runtime 权威后端全量。未合并、未部署、未启动 H2-C、未运行 Playwright。

## 最终裁决

```
STOP_AND_REPORT_CTO_WITH_EXACT_CAUSAL_CLASSIFICATION
```

单一权威运行产出红色 → 按纪律 STOP；**零重跑**。根因是**执行方 launcher 环境缺陷**，非产品/候选/栈缺陷。

## F1 — 精确因果分类

```
EXECUTOR_LAUNCHER_ENVIRONMENT_DEFECT__TEST_DATABASE_URL_EXPORTED_AS_EMPTY_STRING_BY_SHELL_EXPANSION_ORDERING
```

- **机制:** 权威运行以 `env DATABASE_URL='<字面量>' TEST_DATABASE_URL="$DATABASE_URL" ... pytest` 启动——`$DATABASE_URL` 在 `env` 应用 DATABASE_URL **之前**即被 shell 展开 → pytest 进程的 `TEST_DATABASE_URL` 被导出为**空字符串**。
- **证据签名**（environ 转储中 `'TEST_DATABASE_URL': ''` 直接可见）：
  - 29 个 setup ERROR：real_alembic_upgrade 模块断言 TEST_DATABASE_URL 非空；
  - dc11t2_async_test_utils / s4g_migration_infrastructure_hardening / migration_preflight_exact_catalog / reporting_bootstrap_contract 的 "temporary database creation requires TEST_DATABASE_URL" / psycopg2 host 'None' 错误与失败；
  - +21 个条件 skip；
  - conftest 对空串回退 DATABASE_URL，故其余 3646 节点不受影响而通过。
- **范围豁免证明**：产品候选无缺陷证据——预检栈上 env 正确设置时，R3-R1/R3-R2 模块 9/9×2 序、focused 97/97×2 序、pw1r3 7/7（DB15 实证）全绿；crud/user.py 修复路径已被预检门直接覆盖。栈无缺陷（全程无 TooManyConnectionsError，max_connections=300 保持）。
- **处置**: 按指令"任何红色立即 STOP、权威运行后不得重跑 full suite"执行。修复路径建议：CTO 授权一次修正环境的全新权威重跑（launcher 以字面量传递 TEST_DATABASE_URL==DATABASE_URL），或改派执行。

## Phase 1 — 证明门（全 PASS）

candidate `25626f4d` == 远端 tip ✓；parent == `13a8d25c` ✓；BASE_ACCEPTED_SOURCE `0267ea73` 为祖先 ✓；KILO_REVIEW `d6289a6b` 远端存在且父 == candidate ✓；累计 delta 自 BASE_ACCEPTED_SOURCE 恰 **4 文件**（crud/user.py [R3-R1 MissingGreenlet 修复] + R3-R1 测试模块 [9 tests] + 两份台账）✓；detached worktree clean 且 committed blobs 字节一致 ✓。

## Phase 2 — Machine Preflight（PASS；preflight.json 见 evidence）

Lubuntu 原生 / Python 3.12.3 / pytest 9.1.1 / PG16-alpine / Redis7-alpine；两套任务独占栈（预检 15601/16601 已销毁重建；权威 15602/16602）；max_connections=300 实证；非超级用户 CREATEDB 角色 r3r2tester；库名 test_ 前缀；临时库安全门启用；Alembic 37 迁移 → 唯一 head 037；Redis DB0/DB15 双空；REDIS_URL→DB0、PW1R3_TEST_REDIS_URL→DB15；127.0.0.1:26379 connect_ex=111 全程无监听；必需变量仅记存在性；4/4 候选文件严格 UTF-8/无 BOM/LF-only；宿主快照记录。

## Phase 3 — Pre-Gates（全 PASS，预检栈）

| 门 | 结果 |
|---|---|
| R3-R2 模块自然序 | **9/9** |
| R3-R2 模块逆序 | **9/9** |
| focused bundle 收集 | **精确 97** |
| focused 自然序 | **97/97** |
| focused 逆序 | **97/97** |
| pw1r3 | **7/7**（DB15 实证：6 个 rate_limit 键写入 DB15；26379 零连接） |
| 模块运行后残留 | wholesalers=0 / registrations=0 / UUID schemas=0 |
| JwtAuthStrategy | 模块内双层 fail-closed 守卫 + fresh-process spec 层独立探针 = Mock 恢复 |

随后预检栈卷**销毁**并重建第二套全新权威栈；预检结果不计作 full-suite authority。

## Phase 4 — 单次权威全量（RED → STOP）

单次调用（13:15:10 启动，31:06 墙钟），retries=0，无 grep/shard；运行前复证 DB0/DB15 空、Alembic 037、26379 无监听、最终 LF 字节 SHA-256 与作者台账一致（test 文件 `00c64a89…`、crud/user.py `95c89cbd…`）：

| 口径 | collected | passed | failed | errors | plain skipped | xfailed | xpassed | gap |
|---|---|---|---|---|---|---|---|---|
| 期望 | 3773 | 3710 | 0 | 0 | 48 | 15 | 0 | 0 |
| **实测** | 3773 | 3646 | **8** | **35** | **69** | 15 | 0 | 0 |

差异全部由 F1 环境缺陷解释（受影响模块清单见 failure_set.json）。

## Phase 5 — Post-Run Truth（fresh admin connection）

wholesalers=4 / tenant_registrations=0 / UUID schemas=0 / 无临时数据库 / dc11t2fr_% 角色=0 / Redis DB0=6 键（pw1r3 限流键）、DB15=0。wholesalers=4 与已知候选终态首数一致；UUID schemas=0 反映本轮 64 节点缺失（env 缺陷所致），不作残留归因结论。

## Phase 6 — Quality（全 PASS）

py_compile OK；git diff --check OK；scoped pre-commit 全 Passed（exit 0）；detect-secrets 4 候选文件 0 findings；UTF-8/no-BOM/LF-only 4/4；GitNexus analyze（34,422 nodes/56,854 edges）+ status 钉住 `25626f4` ✅；refs 复验未漂移。

## Phase 7 — Evidence（本分支 evidence 目录）

REPORT.md、preflight.json、command/env presence record、消毒后的 raw console + JUnit XML（environ 转储中的 SECRET_KEY/DATABASE_URL 口令/REPORTING_PASSWORD/PLATFORM secrets 已全部 REDACTED）、reconciliation.json、failure_set.json、skip_nodes.txt（69）/xfail_nodes.txt（15）、post_run_residue.txt、cleanup closure、committed-blob manifest。

## Phase 8 — Cleanup（cleanup.md）

容器/卷/网络删除、四端口释放证明、凭据 shred、worktree 移除、refs 不变。

## 裁决链

STOP 归因于执行方环境缺陷而非候选。建议 CTO 二选一：(a) 授权一次修正 launcher 的全新权威重跑；(b) 改派独立执行方复核。候选本身（含 crud/user.py MissingGreenlet 修复）在正确环境下已由预检门强证据支撑（9/9×2、97/97×2、7/7 DB15、0/0/0 残留、JwtAuth 双层恢复）。
