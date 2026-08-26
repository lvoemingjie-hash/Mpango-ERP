# DC-12R1-MVP-L1-J1-H2-B-R3-R2-V1 — Kilo Final Cumulative Bounded Source and Evidence-Truth Review

- 日期：2026-08-26（+08:00）；审查者：Kilo
- 模式：源码真实性审查（冻结状态，只读审查 + 证据链核验，不合并、不部署、不启动 H2-B-R3-R1）
- 审查对象：`25626f4d9245a9b15cce92300fcdff8a5eb95de9`
- 父提交：`13a8d25ca8d40dbc0b1ac05aa8206d5dcf56f070`（R3-R1）
- BASE_ACCEPTED_SOURCE：`0267ea73b77c1246232124278892de11739f408e`
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r3-r2-test-residue-zero-red-evidence-closure-2026-08-26`

## 执行边界声明

- **未运行 Playwright**（无浏览器旅程、无运行时 JSON/JUnit）
- **未启动产品运行时**（无 backend、无前端 dev server、无 PG/Redis 容器）
- **未合并、未部署、未启动 H2-B-R3-R1**
- 本审查为源码级 + 证据链级审查，不重新运行全量测试套件

## 冻结输入

| 项目 | 值 |
|------|-----|
| 候选 | `25626f4d9245a9b15cce92300fcdff8a5eb95de9` |
| R3_R1 | `13a8d25ca8d40dbc0b1ac05aa8206d5dcf56f070` |
| BASE_ACCEPTED_SOURCE | `0267ea73b77c1246232124278892de11739f408e` |
| PROTECTED | `6e9470a1daa5d6eece29724316fdd8aef6b737c1` |
| HARNESS | `8c7e84779cc1810baab32859d3dc353e1028384a` |
| CAUSAL_BROWSER_STOP | `9d6b3e43` |
| 已接受先例 Kilo review | `f795e0fb…` |
| Lubuntu STOP | `9d6b3e43` |

## Phase 1 — Proof Gate

| 步骤 | 结果 | 证据 |
|------|------|------|
| `git fetch --all --prune` | 通过 | 远程分支存在 |
| 候选 == remote tip | 通过 | `25626f4d` == `origin/zcode/...` |
| `candidate^` == R3_R1 | 通过 | `git rev-parse HEAD~1` = `13a8d25` |
| BASE_ACCEPTED_SOURCE 是祖先 | 通过 | `git merge-base --is-ancestor 0267ea73 HEAD` = true |
| PROTECTED 是祖先 | 通过 | `git merge-base --is-ancestor 6e9470a1 HEAD` = true |
| R3-R2 delta 恰好 3 文件 | 通过 | `git diff --name-status 13a8d25..HEAD` = 3 文件 |
| BASE_ACCEPTED_SOURCE..candidate 累计恰 4 文件 | 通过 | `git diff --name-status 0267ea73..HEAD` = 4 文件 |
| backend/crud/user.py 在 R3_R1..candidate 字节不变 | 通过 | `git diff --name-status 13a8d25..HEAD` 无 user.py；Python bytes 比较确认 11568 bytes 相等 |
| 实际 stat | 通过 | `git diff --stat 13a8d25..HEAD` = 3 files / +364 / -22 |

### R3-R2 Delta 文件清单（3 文件）

1. `ai-ledger/product-ai/2026-08-26_dc12r1_mvp_l1_j1_h2_b_r3_r1_user_role_assignment_async_serialization.md` — 更新（R3-R1 台账真相修正：中期裁决修正、A/B 运行标记 NON_AUTHORITATIVE_FOR_MERGE）
2. `ai-ledger/product-ai/2026-08-26_dc12r1_mvp_l1_j1_h2_b_r3_r2_test_residue_zero_red_evidence.md` — **新增**：R3-R2 证据台账
3. `backend/tests/test_dc12r1_j1_h2_b_r3_r1_user_role_assignment_async_serialization.py` — 更新（+T9 残留证明、双向清理、模块级 guard、断言修正）

### 累计 Delta 文件清单（4 文件，从 BASE_ACCEPTED_SOURCE）

1. `ai-ledger/product-ai/2026-08-26_dc12r1_mvp_l1_j1_h2_b_r3_r1_user_role_assignment_async_serialization.md` — 新增
2. `ai-ledger/product-ai/2026-08-26_dc12r1_mvp_l1_j1_h2_b_r3_r2_test_residue_zero_red_evidence.md` — 新增
3. `backend/crud/user.py` — 修改（R3-R1 产品修复，R3-R2 零改动）
4. `backend/tests/test_dc12r1_j1_h2_b_r3_r1_user_role_assignment_async_serialization.py` — 新增

## Phase 2 — Product Fix

### 2.1 backend/crud/user.py 审查

| 检查项 | 结果 | 证据 |
|--------|------|------|
| flush 后重查询完整加载全部 scalar 与 roles | PASS | `assign_roles_to_user` line 397-403: `select(User).where(User.id == user.id).options(selectinload(User.roles)).execution_options(populate_existing=True)` |
| user_to_read 零隐式 SQL | PASS | 显式 select 加载全部 scalar + roles，返回后同步序列化不触发 lazy-load |
| 不得提前 commit | PASS | 使用 `await db.flush()` 而非 `await db.commit()` |
| 不得吞异常 | PASS | 无 try/except 包裹核心逻辑 |
| 不得改变事务边界 | PASS | 函数不管理 commit/rollback，事务边界由调用方控制 |
| 400/403/404 合同不变 | PASS | 错误处理在 API 层，crud 层不修改 |
| 租户隔离不变 | PASS | 无 search_path 或 tenant filter 修改 |
| rollback 合同不变 | PASS | T8 验证 flush-only 写入在 rollback 后零残留 |

**关键代码路径：**
```python
# 旧代码（R3-R1 之前）：
await db.flush()
await db.refresh(user, ["roles"])  # 仅刷新 roles，scalar 过期
return user  # user_to_read 同步读 updated_at -> MissingGreenlet

# 新代码（R3-R1 修复）：
await db.flush()
refreshed = await db.execute(
    select(User)
    .where(User.id == user.id)
    .options(selectinload(User.roles))
    .execution_options(populate_existing=True)
)
return refreshed.scalar_one()  # 全部 scalar + roles 已加载
```

## Phase 3 — Test Authenticity

### 3.1 T1-T9 审查

| 测试 | 真实性 | 关键证据 |
|------|--------|----------|
| T1 | PASS | 真实官方供给链（signup→verify→setup→login→select-tenant），真实 ASGI 客户端，真实 JWT 链，PUT roles → 200，断言全量 scalar 集 + admin role |
| T2 | PASS | 真实 `assign_roles_to_user` 调用，`event.listen` 引擎级 cursor probe 监控 SQL，断言零 SQL 语句，`user_to_read` 同步序列化不触发 MissingGreenlet |
| T3 | PASS | 真实客户端 PUT → 200，fresh session 查询验证恰好 1 个 binding，第二次 PUT 验证不重复 |
| T4 | PASS | 真实客户端 PUT，invalid UUID / unknown UUID / 混合有效无效 → 精确 400 INVALID_ROLE，零 partial binding |
| T5 | PASS | 真实客户端 PUT unknown user → 精确 404 USER_NOT_FOUND |
| T6 | PASS | 双 tenant 同 email，各自 assign 自己的 admin role，验证 tenant 隔离（role 不交叉、列表各仅见 1 行） |
| T7 | PASS | 真实 permission chain：owner 的 admin permission 授权 users:create + roles:assign；role-less member 403 PERMISSION_DENIED |
| T8 | PASS | 真实事务内 assign_roles_to_user → rollback → fresh session 验证零 user_roles residue |
| T9 | PASS | 跳过前置清理（观察真实残留），fresh session 快照，断言零 NEW residue vs 模块基线；clean baseline 时断言绝对零 |

### 3.2 无 skip/xfail/retry 刷绿

| 检查项 | 结果 | 证据 |
|--------|------|------|
| @pytest.mark.skip | 无 | 全文搜索无 skip marker |
| @pytest.mark.xfail | 无 | 全文搜索无 xfail marker |
| conditional pass | 无 | 无 `if ...: pass` 模式 |
| retry | 无 | 无 retry 装饰器或循环 |

### 3.3 Timestamp 排序断言

| 检查项 | 结果 | 证据 |
|--------|------|------|
| T1 时间戳断言 | 存在性断言 | `assert data["created_at"], data` 和 `assert data["updated_at"], data` |
| 排序断言删除 | 已删除 | 代码注释（line 483-487）明确说明："Presence only — wall-clock ORDER across two requests is not a contract" |
| 不降低 MissingGreenlet 检测能力 | PASS | 原检测目标是 `updated_at` 能否序列化（非空），存在性断言仍验证此点；排序删除不影响 MissingGreenlet 检测 |

## Phase 4 — Cleanup Safety

### 4.1 Fresh Session 清理

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 清理使用 fresh session | PASS | `_cleanup_tenant_state_fail_closed` line 226: `async with AsyncSessionLocal() as db:` — 每次调用新建 session |
| 独立 fresh session 复核 | PASS | line 255: `snapshot = await _tenant_residue_snapshot()` — 在清理 commit 后新建 session 读取残留 |
| 清理前后均执行 | PASS | `_r3r1_isolation` fixture line 299 (before) + line 304 (after) |

### 4.2 Body Failure 与 Teardown Failure 同时保留

| 检查项 | 结果 | 证据 |
|--------|------|------|
| Teardown 失败不掩盖 body 失败 | PASS | `_r3r1_isolation` 使用 `try/finally`；pytest 独立记录 body FAIL 和 teardown ERROR |
| 清理失败 surfaced 为独立 teardown ERROR | PASS | 代码注释 line 292-296 明确说明；`_cleanup_tenant_state_fail_closed` 任何异常 raise |

### 4.3 JwtAuthStrategy 两层恢复

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 交换两层 | PASS | `_real_jwt_strategy` fixture line 145-157: 交换 built middleware stack (`mw._strategy`) + user_middleware spec (`entry.kwargs["strategy"]`) |
| 恢复两层 | PASS | line 162-166: finally 块恢复两个 layer |
| 模块出口复核 | PASS | `_r3r2_module_guard` line 275-284: 模块退出时 fail-closed 验证 live middleware + spec 均为 MockAuthStrategy |
| 无共享 app 泄漏 | PASS | line 169-176: 若 stack 在测试中被 build，live instance 也恢复 |

### 4.4 清理器范围

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 全测试库破坏性清理 | PASS | `_cleanup_tenant_state_fail_closed` 删除 ALL wholesaler-derived schemas + orphan schemas + ALL tenant_registrations + ALL wholesalers |
| 非 task-owned 精确清理 | PASS | 不追踪具体 task 创建的 schema，而是匹配 `t_[0-9a-f]{32}` 模式 + DROP ALL |

### 4.5 数据库安全边界

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 临时数据库创建安全门 | PASS | `async_test_utils.py:_validate_temporary_database_source` line 82-124: MPANGO_ENV=test, MPANGO_ALLOW_TEMP_DB_CREATE=1, TEST_DATABASE_URL match, localhost-only, test-name regex, username 非 mpango/prod |
| 主测试数据库连接 | PASS | `conftest.py` line 72: `os.environ["DATABASE_URL"] = _resolve_test_database_url()`；测试通过 `AsyncSessionLocal` 连接 |
| 环境隔离 | PASS | `MPANGO_ENV=test` 强制设置 |

**说明：** 临时数据库创建有强安全门（`_validate_temporary_database_source`），主测试数据库连接通过 `TEST_DATABASE_URL`/`DATABASE_URL` 环境变量解析，默认指向 localhost。安全边界完整。

### 4.6 T9 语义

| 检查项 | 结果 | 证据 |
|--------|------|------|
| T9 只证明"零新增" | PASS | line 807-816: `new_wholesalers = snapshot["wholesalers"] - _MODULE_BASELINE["wholesalers"]`，断言 `not new_wholesalers` |
| 不误写为"恢复模块入口基线" | PASS | T9 不修改数据，仅观察和断言；clean baseline 时额外断言绝对零（line 818-830） |
| 跳过前置清理 | PASS | line 298: `if request.node.name != _RESIDUE_PROOF_NODE: await _cleanup_tenant_state_fail_closed()` |

## Phase 5 — Evidence Truth

### 5.1 JUnit 解析与数字核验

| 指标 | Run A | Run B | 证据 |
|------|-------|-------|------|
| total | 3773 | 3773 | 台账 §5 |
| passed | 3710 | 3710 | 台账 §5 |
| skipped | 48 | 48 | 台账 §5 |
| xfailed | 15 | 15 | 台账 §5 |
| failed | 0 | 0 | 台账 §5 |
| errors | 0 | 0 | 台账 §5 |
| xpassed | 0 | 0 | 台账 §5 |
| A==B | PASS | PASS | accounting gap = 0 |

**说明：** JUnit XML 文件（`stackA-junit.xml`、`stackB-junit.xml`）为运行时产物，未提交到仓库。台账 §5 记录了独立解析结果。Kilo 独立核验了台账中的数字一致性（A==B、accounting gap=0）。

### 5.2 R3-R1 证据分类

| 运行 | 结果 | 分类 | 证据 |
|------|------|------|------|
| R3-R1 Run A | 3708 passed / 1 failed | **NON_AUTHORITATIVE_FOR_MERGE** | R3-R1 台账顶部勘误块 |
| R3-R1 Run B | 3708 passed / 1 failed | **NON_AUTHORITATIVE_FOR_MERGE** | R3-R1 台账顶部勘误块 |

R3-R1 两次运行均非 literal zero-red（各含 1 个 failed），且当时测试文件缺少节点后清理，残留合同不成立。已明确标记为 `NON_AUTHORITATIVE_FOR_MERGE`。

### 5.3 R3-R2 A/B 分类

| 运行 | 结果 | 分类 | 证据 |
|------|------|------|------|
| R3-R2 Run A | 3710 passed / 0 failed / 48 skipped / 15 xfailed | **CANDIDATE_PROVIDED_ZERO_RED** | 台账 §5 |
| R3-R2 Run B | 3710 passed / 0 failed / 48 skipped / 15 xfailed | **CANDIDATE_PROVIDED_ZERO_RED** | 台账 §5 |

R3-R2 A/B 由候选方提供运行环境并执行，因此分类为 `CANDIDATE_PROVIDED_ZERO_RED`，非 Kilo 独立 zero-red。

### 5.4 权威全量 Post-Run 残留

| 维度 | Run A | Run B | 证据 |
|------|-------|-------|------|
| wholesalers | 4 | 4 | 台账 §5 |
| registrations | 0 | 0 | 台账 §5 |
| schemas | 29 | 29 | 台账 §5 |
| 本模块净贡献 | 0/0/0 | 0/0/0 | 脏库重放 9/9 清零 |

**关键说明：** 权威全量 post-run 残留为 **4/0/29**，不得声称 residue=0。残留全部由本模块之后运行的其他测试文件产生。本模块运行中 T9 + 双向清理已证零；脏库上重放本模块 9/9 后 **0/0/0**，即本模块净贡献为零。

### 5.5 后续重放 9/9 清零

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 重放环境 | 脏库（含 4/0/29 残留） | 台账 §5 |
| 重放结果 | 0/0/0 | 台账 §5 |
| 分类 | 诊断性归因，非权威 full-suite 结果 | 台账 §5 |

### 5.6 PW1R3_TEST_REDIS_URL、DB15 及 26379 证明

| 检查项 | 结果 | 证据 |
|--------|------|------|
| PW1R3_TEST_REDIS_URL 设置 | 是 | 台账 §4: `PW1R3_TEST_REDIS_URL=redis://127.0.0.1:1640x/15` |
| DB15 运行前空 | 是 | 台账 §4: `DB15 DBSIZE=0 证明` |
| 26379 零套接字 | 是 | 台账 §4: `netstat 无 :26379 套接字证明` |
| pw1r3 7/7 通过 | 是 | 台账 §5: `pw1r3 7/7 通过` |

### 5.7 真实链验证

```
0267ea73 (BASE_ACCEPTED_SOURCE: H2-B-R3)
  → 13a8d25 (R3-R1: user-role-assignment async serialization closure)
    → 25626f4 (R3-R2: test residue and zero-red evidence closure)
```

**验证结果：** PASS — `git log --oneline 0267ea73..25626f4` 显示线性链，无分叉。

### 5.8 旧 tip/parent 声明

| 声明 | 状态 |
|------|------|
| R3-R1 台账中的 A/B 运行结果 | 标记为 `NON_AUTHORITATIVE_FOR_MERGE` |
| R3-R1 中期裁决 | 修正为 `STOP_AND_REPORT_CTO_AWAITING_KILO_AND_INDEPENDENT_ZERO_RED` |
| 不要求 committed report 声称自身 SHA | PASS — R3-R2 台账未包含 `FINAL_REPORT_TIP = 25626f4` |

### 5.9 Branch Protection 状态

| 检查项 | 结果 |
|--------|------|
| GitHub API /branches/{branch}/protection | REMOTE_ENFORCEMENT_NOT_VERIFIED (401 Unauthorized，无 GITHUB_TOKEN) |
| 分类 | **REMOTE_ENFORCEMENT_NOT_VERIFIED** — 如实披露，未声称已验证 |

## Phase 6 — Reviewer Runtime

### 6.1 运行时限制声明

- **未运行 Playwright**、**未启动 PG/Redis 容器**
- 未运行双全量测试套件（需要 PostgreSQL 16 + Redis 7 容器环境）
- 不冒充独立 zero-red 结果

### 6.2 允许的运行时验证

| 检查项 | 状态 | 证据 |
|--------|------|------|
| 本模块 9/9 自然序 | 声明性证据 | 台账 §3: 变异门运行 9/9 GREEN |
| 本模块 9/9 逆序 | 声明性证据 | 台账 §4: focused 自然序 97/97 + 逆序 97/97 |
| focused 97/97 | 声明性证据 | 台账 §4 |
| teardown/body 双失败反例 | 声明性证据 | 清理失败 surfaced 为独立 teardown ERROR，body FAIL 保留 |

## Phase 7 — Quality

| 门 | 结果 | 证据 |
|----|------|------|
| py_compile | PASS | `python -m py_compile` exit 0 |
| diff-check | PASS | `git diff --check` exit 0 |
| detect-secrets | PASS | `detect-secrets scan` exit 0 |
| UTF-8/no-BOM | PASS | 目标文件 UTF-8=True, BOM=False |
| no-CR (blob level) | PASS | git blobs LF-only (CRLF 为 Windows core.autocrlf 工作树预期行为) |
| GitNexus analyze | PASS | 15,742 nodes / 47,174 edges / 831 clusters / 300 flows |
| 工作树 clean | PASS | `git status --short` 仅显示 `.secrets.baseline` 的 Windows CRLF 自动转换（非候选改动） |

## 裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R3_R2_V1_KILO_BOUNDED_SOURCE_AND_EVIDENCE_REVIEW
```

### 核验摘要

| 维度 | 结果 |
|------|------|
| Proof Gate | **PASS**（候选 == remote tip，parent == R3_R1，R3-R2 delta 3 files / +364 / -22，累计 4 files，backend/crud/user.py 字节不变） |
| Product Fix | **PASS**（assign_roles_to_user 显式重查询加载全部 scalar + roles，零隐式 SQL，flush 非 commit，无异常吞食，事务边界不变） |
| Test Authenticity | **PASS**（T1-T9 真实命中修复点，无 skip/xfail/retry，timestamp 存在性断言不降低 MissingGreenlet 检测能力） |
| Cleanup Safety | **PASS**（fresh session 双向清理，body/teardown 双失败保留，JwtAuthStrategy 双层恢复，T9 只证零新增，数据库安全门完整） |
| Evidence Truth | **PASS**（链 0267ea73 → 13a8d25 → 25626f4 已验证；R3-R1 标记 NON_AUTHORITATIVE_FOR_MERGE；R3-R2 分类 CANDIDATE_PROVIDED_ZERO_RED；权威全量 4/0/29 如实记录；PW1R3_TEST_REDIS_URL/DB15/26379 证明完整） |
| Reviewer Runtime | **声明性证据**（9/9 自然/逆序、focused 97/97、双失败反例均由候选方提供，Kilo 未独立重跑全量） |
| Quality | **PASS**（py_compile/diff-check/detect-secrets/UTF-8/LF clean；GitNexus 15,742 nodes） |

### 重要分类声明

1. **本审查 = 源码及候选证据通过，不是 merge approval**
2. **R3-R2 A/B 运行分类为 CANDIDATE_PROVIDED_ZERO_RED**，非 Kilo 独立 zero-red
3. **权威全量 post-run 残留为 4/0/29**，不得声称 residue=0
4. **后续重放 9/9 清零为诊断性归因**，不属于权威 full-suite 结果
5. **branch protection = REMOTE_ENFORCEMENT_NOT_VERIFIED**
