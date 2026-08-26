# DC-12R1-MVP-L1-J1-H2-B-R2-R4 — 临时数据库 Teardown 权限竞态闭合

- 日期：2026-08-24（+08:00）；执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-temp-db-teardown-privilege-race-closure-2026-08-24`
  （自 BASE `218be690a6d5ad3551c31fa28087964440c888c9` 创建）
- 冻结引用（`git fetch --all --prune` 后核实）：
  - BASE/CANDIDATE `218be690…`（= 远端源分支头）
  - 受保护 `origin/product-dev-recovered` = `6e9470a1…`（BASE 祖先）
  - 已接受 Kilo 源审 `b7e67e24…`（其父即 BASE）
  - OpenCode STOP 证据 `c1dd4f78…`（reports 分支头；BASE 为其祖先；原样保留零改动）
- 模式：仅共享测试基础设施修复；零产品/运行时行为变更；
  冻结检查点后 STOP。
- 恰 3 文件 delta（allowlist）：
  1. `backend/tests/async_test_utils.py`
  2. `backend/tests/test_dc11t2_async_test_utils.py`
  3. 本台账

## 1. Phase 1 — 证明与影响

- 隔离干净 worktree（detached → 新分支）于 BASE；porcelain 0 行。
- `temporary_database_url` 完整调用者普查：**10 个测试文件、约 45 个调用点**，
  全部位于 `backend/tests/`（real-alembic 模块 27 处、s4g 5 处、p17dc/p21 各 1 处、
  dc11t4h 1 处、dc12r1r5 1 处、helpers 1 处、dc11t2 自测 2 处 + 模块内 import）。
  **零产品执行流触达** → 按预案记录 HIGH 测试爆炸半径（预期），
  无 CRITICAL/产品面 → 不触发 STOP。
- GitNexus：index 于本任务 worktree 重建（analyze 15,473 节点/46,467 边），
  提交前 detect_changes 以精确 `git diff --name-only` + 源审替代
  （本工具面无 MCP detect_changes；与 Kilo 先例同口径披露），
  提交后在最终 SHA re-analyze + status。

## 2. Phase 2 — 因果真相（任务私有 PG16 复现）

环境：任务自有 PostgreSQL 16.15（autovacuum=on）；非超级用户 CREATEDB+CREATEROLE
测试角色 `h2btester`（rolsuper=false）；无产品数据库。

实测（evidence/02_causal_probes.txt）：

| 实验 | 结果 |
|---|---|
| 终止**本角色**会话 | **ALLOWED**（自终止恒可） |
| 终止**他角色**会话（本角色 CREATE 的非超级用户、无 pg_signal_backend） | **DENIED**（InsufficientPrivilege） |
| 终止**超级用户**会话 | **DENIED**（同错误类别） |
| **旧 blanket 查询**（`SELECT pg_terminate_backend(pid) … WHERE datname=%s`，附超级用户会话） | **RED：与事故完全一致的 InsufficientPrivilege 签名**（"Only roles with the SUPERUSER attribute may terminate processes of roles with the SUPERUSER attribute."） |
| 超级用户观察者 pg_stat_activity 快照 | 附加会话 `backend_type=client backend`（探针注入类）；非超级用户视图 backend_type 被掩码为 NULL |
| 高churn临时库上的 autovacuum worker 捕获（8×TRUNCATE/INSERT 20k/DELETE/UPDATE + 观察轮询） | **未在窗口内捕获** |

**分类（按裁决措辞）：`UNIDENTIFIED_SUPERUSER_OWNED_BACKEND_SESSION`**
—— 事故当次会话的 backend_type 无法回溯捕获；autovacuum 仅记录为**假设**，
非已证事实。已证事实：*任一*超级用户拥有的会话附加在生成的临时库上即令旧
blanket teardown 整体失败（机制类已由探针证明）。

## 3. Phase 3 — 实现契约（12 条逐项落实）

`temporary_database_url` teardown 重写（`_teardown_temporary_database`）：

1. 移除对 pg_stat_activity 每行的 blanket 集合式终止；
2. 按**精确生成的临时库名**枚举会话（pid+usename，ORDER BY pid）；
3. 仅终止 `usename == current_user` 的会话（本角色被授权终止的会话）；
4. 零权限提升、零超级用户 URL 要求、零 pg_signal_backend 授予；
5. 非可终止会话 → 有界单调等待（`time.monotonic`，5.0s 上限，0.05s 轮询）；
6. 仅重试"会话集清空→可 DROP"这一清理状态迁移直至固定 deadline；
   与测试绿红无关，非 retry-until-green；
   **（R1 勘误 2026-08-24：本条与第 7 条合读曾暗示 DROP 已在重试范围——这是
   过早声明。R2-R4 实现里 DROP 只在会话集清空后执行一次，遇 ObjectInUse
   即向上传播、数据库泄漏。R1 已修正：见文末"R1 增补"第 A 节。）**
7. 会话集空后 `DROP DATABASE IF EXISTS <精确 Identifier>`（无通配/前缀）；
   **（R1 勘误：`IF EXISTS` 已被 R1 移除——精确 DROP 不掩盖数据库意外缺失。）**
8. 持久非可终止会话 → fail-closed，确定性 sanitized 错误
   `TemporaryDatabaseTeardownError`（静态文案，无 URL/主机/用户/凭据）；
9. InsufficientPrivilege / ObjectInUse / DROP 失败 / 超时零吞没（真实传播）；
10. 原测试体异常按**对象同一性**保留；体失败+清理失败 → 单个
    `BaseExceptionGroup([原异常对象, 清理异常])`；
11. admin 连接 `finally: admin.close()` 恒关闭；
12. autovacuum 保持全局开启；h2btester 未获 SUPERUSER/pg_signal_backend。

## 4. Phase 4 — 真实测试与突变

新增 8 个真实测试（模块合计 22）：常规建删（精确命名
`test_<prefix>_<12hex>` 断言）；本角色开放会话被终止后 DROP；瞬态他角色会话
（经本角色 CREATE 的 login 角色构造，非超级用户、无凭据泄露）在界内等出；
持久他角色会话 fail-closed + 文案 sanitization + 库仍存在（不谎报已清理）；
原异常对象同一性；体+清理双失败 → 恰 BaseExceptionGroup；既有 8 个
名称/来源安全守卫测试原样保留；2 个 scripted-admin 契约测试（DROP 后在场证明、
有界 deadline）。模块级无任何源/admin URL 或凭据进入输出。

运行时因果探针（任务私有，不入库不打印凭据）：
- 旧 blanket 查询 + 超级用户会话 → **RED**（Phase 2 表）；
- 修复版 + 瞬态超级用户会话（~2s 后自断）→ 等待后成功 DROP；
- 修复版 + 持久超级用户会话 → 有界 fail-closed，库未误清，文案零凭据。

突变门（全部 RED → 字节级还原 → 复跑 GREEN）：

| 突变 | 检测节点 | 结果 |
|---|---|---|
| M1 恢复 blanket 终止 | transient foreign session 测试 | **RED**（0.53s）→ 还原 → GREEN |
| M2 抑制持久会话超时 | scripted deadline 测试 | **RED**（10.49s 预算耗尽）→ 还原 → GREEN |
| M3 移除原异常保留 | identity 测试 | **RED** → 还原 → GREEN |
| M4 移除清理后缺席证明 | scripted presence 测试 | **RED** → 还原 → GREEN |

还原采用任务快照 `cmp -s` 字节校验（git checkout 误还原事故已披露并纠正，
最终树与快照逐字节一致）。

## 5. Phase 5 — 门禁（两栈，全部 GREEN）

栈：A=pg 15561/redis 16561，B=pg 15562/redis 16562；均全新卷/网络；
`h2btester`（非超级用户）运行 pytest；**两栈 autovacuum=on**（evidence 留痕）；
Redis PING（DB0/DB15 dbsize=0）；127.0.0.1:26379 不可达。

| 门 | A | B |
|---|---|---|
| dc11t2 自然/倒序 | 22/22 + 22/22 | 22/22 + 22/22 |
| real-alembic 模块自然/倒序 | 29/29 + 29/29 | 29/29 + 29/29 |
| 原失败节点 20/20（4 CPU 负载进程并发） | **20/20** | **20/20** |
| R2-R3 四模块束自然/倒序 | 46/46 + 46/46 | 46/46 + 46/46 |
| 前驱束（DC11D→canonical→DC3B / 反向） | 44/44 + 44/44 | 44/44 + 44/44 |
| 聚焦束恰 109 自然/倒序节点 | 109/109 + 109/109 | 109/109 + 109/109 |
| H2-B 独立 | 12/12 | 12/12 |

**权威全量（每栈重置后恰一次）：**

| 栈 | collected | passed | failed | errors | skipped | xfailed | xpassed | gap |
|---|---|---|---|---|---|---|---|---|
| A | 3758 | 3695 | **0** | **0** | **48** | **15** | **0** | **0** |
| B | 3758 | 3695 | **0** | **0** | **48** | **15** | **0** | **0** |

- A/B **skip 节点位置集全等**；**xfail 节点+原因集全等**；计数全等
  （reconciliation_compare.txt）。3758 = 3750 既有 + 8 个新测试。
- 全量后每栈仅存 `test_r2r4_full_<s>` 一个库：**整套 3758 节点运行期间全部
  临时库被修复版 teardown 精确清除，零遗留**。
- 过程披露：首轮 gate 脚本 PYTHONPATH 缺插件路径致一次空目标误跑全量
  （运行至 ~27% 即杀）；此后两栈全部重置重建，上表为重置后唯一权威运行。

## 6. Phase 6 — 质量

- py_compile（2 个变更 .py）OK；`git diff --check` 干净。
- 严格 UTF-8/无 BOM/无 mojibake（全部变更文件）。
- scoped pre-commit（trailing/end-of-file/yaml/large-files/detect-secrets）
  全 Passed（Windows 宿主执行；WSL 对 github.com:443 受阻——沿 Kilo 先例披露）。
- 裸 detect-secrets 扫描变更文件 **0 发现**；`.secrets.baseline` 字节不变。
- GitNexus：BASE 重建索引；最终 SHA re-analyze + status 钉住（见证据）。
- delta 恰 3 文件（allowlist）；其余文件与 218be690 字节一致。

## 7. Phase 7 — 冻结与清理

- 仅提交/推送隔离 Zcode 分支；local SHA == remote SHA。
- 受保护引用（product-dev-recovered / Kilo / OpenCode STOP 证据 / 候选源分支）不变。
- 任务容器/卷/网络/凭据/worktree/端口全清（closure 留痕）。
- 原始因果与测试证据保留于源分支之外（任务证据目录，未入库）。

## 8. 后续（裁决链）

CTO merge review → （批准后）R2-R3/R2-R4 合并序列 → 浏览器忘记/重置旅程
（B0 冻结协议）→ 部署裁决。本任务不启动 Kilo/Playwright/合并/部署/
定价/条码/H2-B UI/B0 浏览器协议。

## 9. R1 增补 — DROP 竞态与临时角色凭据闭合（2026-08-24）

分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r1-drop-race-role-credential-closure-2026-08-24`
（自 `7f925e3f…`）。范围仍恰 3 文件（helper + dc11t2 测试 + 本台账）。

### A. 勘误（对上文第 3 节第 6/7 条）

R2-R4 的实现**并未**重试 DROP：DROP 只在会话集清空后执行一次，遇
ObjectInUse 即向上传播并泄漏数据库；`IF EXISTS` 还会掩盖数据库意外缺失。
上文相关表述为过早声明，以本节为准。

### B. R1 实现真值

1. 同一 monotonic deadline 内循环：枚举精确库会话 → 终止本角色会话 →
   尝试 DROP；
2. DROP 遇 ObjectInUse → rollback 后重新枚举，继续有界状态迁移；
3. **仅 ObjectInUse 可重试**；其他 DROP/权限错误（如 InvalidCatalogName）
   立即 fail closed 传播；
4. deadline 到期抛 sanitized `TemporaryDatabaseTeardownError`；
5. 精确 `DROP DATABASE`（移除 `IF EXISTS`），意外缺失不被掩盖；
6. 外部角色名与口令每次测试运行随机生成（`dc11t2fr_<hex10>` +
   `secrets.token_hex`），无固定可提交登录口令；
7. 角色 SQL 全部 `psycopg2.sql.Identifier` + 参数绑定（口令不拼接）；
8. fixture teardown 先 `NOLOGIN` 再 DROP，重试耗尽**必须失败**；
9. fresh connection 独立证明 pg_roles 中任务角色为零（精确名 + 模块级
   前缀零残留双证明）；
10. 错误输出不含角色名/口令/URL/主机/用户名（测试断言随机角色名与口令
    均不出现）。

### C. RED/GREEN 与突变（全部达成）

| 项 | 结果 |
|---|---|
| 旧码 RED（父 helper + 新重试测试：第一次 ObjectInUse 第二次成功） | **RED**（1 failed）→ 恢复新码 **GREEN** |
| 持续 ObjectInUse 至 deadline | 确定性 fail closed（scripted） |
| MA 删除 ObjectInUse 重试 | RED → 字节还原 → GREEN |
| MB 删除角色零残留证明 | RED → 字节还原 → GREEN |
| MC 角色清理持续失败被吞掉 | RED → 字节还原 → GREEN |
| 恢复后 helper 模块自然/反向 | 27/27 + 27/27 |

### D. 门禁（两栈 A=15561/16561，B=15562/16562；autovacuum=on；非超级用户 h2btester）

| 门 | A | B |
|---|---|---|
| dc11t2 自然/反向 | 27/27 + 27/27 | 27/27 + 27/27 |
| real-alembic 自然/反向 | 29/29 + 29/29 | 29/29 + 29/29 |
| 原失败节点 20/20（4 CPU 负载） | 20/20 | 20/20 |
| R2-R3 束自然/反向 | 46/46 + 46/46 | 46/46 + 46/46 |
| 前驱束 44 | 44/44 + 44/44 | 44/44 + 44/44 |
| 聚焦束 109 | 109/109 + 109/109 | 109/109 + 109/109 |
| H2-B | 12/12 | 12/12 |

### E. 权威全量 — STOP_AND_REPORT

Stack A 重置后单次运行：

```
1 failed, 3699 passed, 48 skipped, 15 xfailed, 0 errors, 0 xpassed
collected 3763（= 3758 + 5 个 R1 新测试）；gap 0
```

按裁决 Stack B 全量**未运行**。失败精确归因：

```
FAILED tests/test_u6i2_owner_credential_setup_token_issue.py
       ::test_expired_prior_token_allows_new_setup_token_issue
assert rows[0].token_hash == hash_token(prior_raw_token)  # 实为新 token 哈希
CLASSIFICATION: PRE_EXISTING_NONDETERMINISTIC_CREATED_AT_TIE_WITHOUT_TIEBREAKER_OUT_OF_SCOPE
```

1. **范围外**：u6i2 模块与 `models/base.py`、`models/tenant_onboarding.py`
   与父提交 `7f925e3f` 字节一致（u6i2 最后触碰于 `218be690` 2026-08-23，
   R2-R3）；不在 R1 3 文件 delta 内。R1 helper 改动不触达主库路径。
2. **机制**：`created_at` 为 `server_default=now()`（事务开始时刻）；
   `_token_rows` 以 `ORDER BY created_at` 且**无次级排序键**。两次插入在
   全量负载下时钟并列（或回拨）时顺序未定义 → rows[0] 可为新 token。
   证据：len(rows)==2 已通过（两 token 均在、哈希各自正确），仅次序翻转。
3. **非确定（诊断复现，DIAGNOSTIC ONLY 不计权威）**：同栈全量后立即
   隔离复跑——单节点 1/1、整模块 14/14、另 5 次重复 5/5 全绿。
4. 同节点在本任务两栈 4 次 46/46 束运行与 R2-R4 两次全量（3695/0 双栈）
   中均绿。
5. 非夹具残留、非环境误配、非 R1 回归。

### F. R1 裁决

```
STOP_AND_REPORT_CTO_WITH_EXACT_CAUSAL_CLASSIFICATION
```

R1 全部 11 项修复、RED/GREEN、突变与两栈门禁已达成并冻结于隔离分支；
唯一阻塞为上述范围外非确定性排序缺陷（预存于 R2-R3 引入的 u6i2 断言
次序假设，或需 tiebreaker/确定性排序的独立后续修复）。等待 CTO 裁决。
