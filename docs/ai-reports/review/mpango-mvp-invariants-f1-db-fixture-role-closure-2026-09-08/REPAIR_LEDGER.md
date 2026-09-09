# REPAIR_LEDGER — MPANGO-MVP-INVARIANTS-F1-DB-FIXTURE-ROLE-CLOSURE（2026-09-08/09）

AUTHORIZATION_ID=CTO-AUTH-MPANGO-MVP-INVARIANTS-F1-DB-FIXTURE-ROLE-CLOSURE-2026-09-08
EXECUTOR=ZCode-W；VERIFICATION_TIER=V3_REQUIRED_FOR_FINAL_ACCEPTANCE（本轮为
BOUNDED_IMPLEMENTATION_AND_REAL_DB_INTEGRATION_EVIDENCE，开发/候选证据，不占用已停止的 V3-R1）。
CLAIM_CEILING=TEST_FIXTURE_ROLE_SEPARATION_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW_ONLY。

## 1. 基线与候选身份

| 项 | 值 |
|---|---|
| BASE | `76ab895fe6e00c91af09cef7b938be074734b461`（fetch 后与远端一致；父 `69495712ad…`） |
| 产品基线 | `a516d2b3…`（冻结未动）；产品目标 `bd2373cb…` |
| 分支 | `zcode/mpango-mvp-invariants-f1-db-fixture-role-closure-2026-09-08`（自 BASE 普通提交） |
| worktree | `C:/Users/Jeff0/MPANGO ERP/worktrees/zcode_mpango_mvp_invariants_f1_role_closure_2026-09-08` |
| 候选范围 | 恰四个路径：M `backend/tests/mpango_invariants_r0_support.py`；M `backend/tests/test_mpango_invariants_r0_r1_guards.py`；A `backend/tests/test_mpango_mvp_invariants_db_fixture_roles.py`；A 本文件。以 `git diff --name-only 76ab895f` 为准（唯一路径集，不做窗口相加） |
| 冻结面 | 产品 API/services/auth/core/模型/迁移/tenant bootstrap/全局 conftest/Redis F1 语义/经济不变量零改动（diff 为空核验） |

## 2. 三身份合同

| 身份 | 绑定 | 权责 |
|---|---|---|
| bootstrap/迁移 | 容器 `POSTGRES_USER` == `MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL` 的 user | 仅在子进程中执行真实 alembic 001..037；迁移后执行唯一一次对象所有权对齐（§4 F7）；不承载任何测试会话连接 |
| 测试会话 | `TEST_DATABASE_URL`(==`DATABASE_URL`) 的 user，单独声明 | 普通角色（rolsuper/rolcreatedb/rolcreaterole/rolreplication 全 false、零角色成员关系）；应用 engine、AsyncSessionLocal、产品 bootstrap、teardown 的唯一身份 |
| reporting | 迁移 011 创建的 `reporting_role`/`reporting_user` | 只读；本套件不以其连接；存在性由真实迁移产生 |

拒绝点（全部先于业务写入）：声明缺失（含新 MIGRATION_URL）、TEST!=DATABASE、非 loopback、
无库名/无用户、owner 标签命名空间、迁移目标≠运行目标（同容器/端口/库强绑定）、运行用户==迁移
用户、docker inspect 标签/镜像/端口/POSTGRES_DB/POSTGRES_USER 绑定、engine 目标与用户绑定、
迁移身份活探针（session_user/current_user/库/PG16）、运行身份活探针（同前+角色能力+零成员）、
迁移子进程 rc!=0（脱敏）、head!=037（运行连接读取）、迁移后权限就绪探针失败或不可读
（GUARD_REFUSED_RUN_ROLE_PRIVILEGES 具名分类）。

## 3. conftest 环境改写核查（指令要求）

`backend/tests/conftest.py` 在 import 期执行 `os.environ["DATABASE_URL"] =
_resolve_test_database_url()`：优先取 `TEST_DATABASE_URL`。因此进程内 DATABASE_URL 最终等于
TEST_DATABASE_URL，且发生在 `database.session` 引擎创建之前（引擎按该值构建）——与合同一致：
engine 用户 == 运行身份（并经 `_assert_engine_binding` 与运行连接 `session_user` 双重实证）。
conftest 不触碰 `MPANGO_INVARIANTS_R0_MIGRATION_DATABASE_URL`；亦不重写 `MPANGO_ENV`（守卫另行实证）。

## 4. 权限/对象表（真实消费需求 → 供给方式 → 就绪验证）

| # | 权限/对象 | 消费代码路径 | 供给方 | 就绪验证 |
|---|---|---|---|---|
| P1 | CONNECT ON DATABASE | 一切 | env 供给（bootstrap） | 连接成功本身 |
| P2 | CREATE ON DATABASE | `TenantIdentity.create`→`CREATE SCHEMA` | env 供给 | has_database_privilege CREATE |
| P3 | USAGE+CREATE ON SCHEMA public | bootstrap 替换公共函数、公共对象访问 | env 供给 | has_schema_privilege×2 |
| P4 | SELECT/INSERT/UPDATE/DELETE ON public.wholesalers/retailers/wholesaler_retailer_bindings | seed_public_tenant_rows/drop_tenant | env 供给（默认权限覆盖迁移新建表） | has_table_privilege×4×3 |
| P5 | SELECT ON public.alembic_version | 夹具 head 验证 | env 供给（默认权限） | head 读取 + has_table_privilege |
| P6 | USAGE ON public 序列 | 公共表序列默认值消费 | env 供给（默认权限） | information_schema 反查零缺失 |
| P7 | public.prevent_ledger_modification() OWNER（+EXECUTE） | bootstrap `CREATE OR REPLACE FUNCTION`（PG 非属主禁止替换；该函数是 bootstrap 替换的**唯一**公共对象） | **夹具迁移后对齐**（迁移身份 `ALTER FUNCTION ... OWNER TO <run>`，幂等、白名单唯一对象、无 REASSIGN OWNED/跨库） | pg_proc.proowner==run + has_function_privilege EXECUTE |
| P8 | 租户 schema 内全部 DDL/DML | bootstrap 建表/索引/视图/触发器/授权 reporting；teardown DROP SCHEMA | 运行身份自建 schema 即属主 | 正控生命周期实测（非仅 SELECT 1） |
| P9 | reporting_role 存在与授权 | bootstrap GRANT | 迁移 011（真实） | 正控中真实 bootstrap 执行 GRANT 成功 |

说明：这是**测试/供给操作角色**的授权表（P2/P3/P7 为 DDL 级），不是生产纯 DML 最小权限认证；
未通过继承 bootstrap/超级用户满足任何对象权限（运行角色零成员关系实证）。

## 5. 代码路径 → 测试矩阵

| 代码路径 | 测试（nodeid 摘要） |
|---|---|
| 同步守卫全链（含迁移绑定/身份分离/engine 绑定） | `test_f1_guard_migration_wrong_target_refuses_pre_launch[host|port|database|user]`、`..._wrong_container_and_owner_refuse_pre_launch`、`..._run_identity_bootstrap_refuses_pre_write`、`..._engine_bound_to_foreign_user_refuses`；guards `test_f1_guard_refuses_missing_migration_url`、`..._migration_target_mismatch`、`..._run_user_equal_to_bootstrap` |
| 迁移子进程仅用迁移 URL、父环境不变、失败脱敏 | `test_f1_migration_subprocess_env_carries_only_migration_url`、`..._failure_is_sanitized_named_refusal` |
| 迁移/运行双身份活探针 + 真实 001..037 + head + 就绪 + 完整生命周期 | `test_f1_positive_role_separated_full_lifecycle`（同一已提交 `r0_task_database` 会话夹具；单独执行亦然） |
| 夹具六阶段对全不变量家族的兼容 | 聚焦运行（§6 run9）覆盖 guards/concurrency/revocation/db_fixture_roles 四文件 |
| F1 Redis 语义回归 | guards 基线 51 节点按 nodeid 保留（collect 前后差集=∅，仅新增 3） |

## 6. 开发各次运行记账（原始日志：§10 证据根）

| # | 范围/env | 结果 |
|---|---|---|
| 1 | 新文件/env_main | 10 error——夹具未注册（缺 import `r0_task_database`）→ 修正 |
| 2 | 同上 | 2 FAILED——计数器误吞真实 docker inspect → 改为仅拦 alembic 子进程、余委托原实现 |
| 3 | 新文件 | **10 PASS**（正控含真实迁移+生命周期） |
| 4 | guards+concurrency | 2 guard NameError（助手局部导入）→ 修正；concurrency 仅已知双退 RED |
| 5 | guards | **54 PASS**（51 基线+3 新） |
| 6 | 正控节点/env_weakrun | setup ERROR=**GUARD_REFUSED_RUN_ROLE_PRIVILEGES**（InsufficientPrivilege: alembic_version，具名包裹、未进测试体） |
| 7 | 正控节点/env_neg | setup ERROR=**GUARD_REFUSED_MIGRATION**（真实子进程在真实空库 read-only 下 CREATE TABLE 失败，脱敏） |
| 8 | 正控节点单独执行 | **1 PASS**（两身份 F1 EVIDENCE 行：inv_f1_boot / inv_f1_run，caps 全 false） |
| 9 | 四文件聚焦/env_main | **83 PASS + 1 已知双退 RED + 2 缓存前提显式 SKIP**（BASE 语义：不可达且未声明任务 Redis→先证明后 ping→前提不可建立即 SKIP） |
| 10 | 四文件聚焦/env_main（最终字节绑定，含 pragma 修正后） | **83 PASS + 1 已知双退 RED（nodeid 与既往一致）+ 2 缓存前提显式 SKIP**；运行后残留核查 t_%=0/wholesalers=0/retailers=0 |

变异（隔离材料 /tmp/f1role_bak，恢复后 sha256 `66f40141…` 字节一致，均重转绿）：
M1 子进程退回运行 URL → 子进程环境契约节点 RED；M2 去同库绑定 → 错目标[port|database]+guards 目标差 RED（3 节点）；M3 允许运行=bootstrap → 两身份分离节点 RED（2 节点）。

## 7. 负面路径与未覆盖

- 已证负面：错目标×4（零子进程启动）、错容器/错 owner（零启动）、运行=bootstrap（写入前拒绝）、
  engine 外用户、弱运行角色（就绪拒绝）、弱迁移身份（真实迁移失败）、迁移失败脱敏。
- 未覆盖/边界：迁移身份"角色属性级"弱化——PG16 禁止剥夺 bootstrap 超级用户（真实报错存证
  `pg16_bootstrap_demotion_refused.txt`），故以只读库载体证同一拒绝链；多容器并发运行未测；
  reporting 身份行为未测（属 011 合同）；正式矩阵 A/B/C 由独立 V3 执行，本轮不重跑。
- 两个既有产品 RED（并发重复退货、缓存同键跨租户读）未获修复结论，维持登记。

## 8. 迁移与连接实证（run3/run8/run9）

真实 001..037 由 `inv_f1_boot` 子进程完成（env_main；空库首跑于 run3 前置阶段完成并持续幂等）；
运行连接 `inv_f1_run` 读取 head==`037_payment_declarations_schema`；两连接同容器
（`mpango-zcode-inv-f1role-dev-pg`，127.0.0.1:60507/inv_f1_lab）不同用户；运行角色
caps=(login=t, super/createdb/createrole/replication=f)、成员关系 0；正控生命周期
（bootstrap→seed→read→drop→零残留）与聚焦运行后残留核查（t_%=0、wholesalers=0、retailers=0）。

## 9. 工具与提交前核查

- GitNexus：主仓索引停在 `218be690`（CTO 已记录）；对本任务 worktree 执行 `gitnexus analyze
  --skip-agents-md` 后 `impact <symbol> --repo <本任务索引>`——结果记录于证据根
  `gitnexus_impact.txt`；`detect-changes` CLI 1.5.3 不存在（历史记录一致），以 `git diff
  --name-only` 唯一路径集 + 暂存 diff 逐文件核对替代，不以文件计数冒充图分析。
- 秘密扫描：真实 `detect-secrets-hook.exe` v1.5.0（完整 AWS-key 字面量反例 rc=1 证非空操作；
  argv/rc 与两次早期尝试的更正记录于 `detect_secrets_run.txt`）；对最终 4 路径正式扫描 **rc=0**；
  `.secrets.baseline` sha256 前后一致（`f49c8622…`）；`git diff --check` 干净；提交 blob
  UTF-8/无 BOM；env/provision 脚本仅存证据根（合成口令，不入库）。扫描处置记录：(a) 守卫
  单测中假 URL 的密码段已移除（守卫仅解析 user/host/port/db，语义不变）；(b) 脱敏测试中两处
  **故意**的假凭据字面量（其存在正是被测对象——验证输出脱敏会剥掉该形状）按 hook 指引标注
  inline `# pragma: allowlist secret`，均已在代码注释中说明意图。
- 资源：两任务容器（dev/neg，标签核验）+ 匿名卷在报告核验后删除；worktree 保留；凭据仅存在于
  证据根脚本与运行日志已脱敏复查。

## 10. 证据根与既有证据定位

- 本任务证据根（绝对宿主路径）：
  `C:\Users\Jeff0\MPANGO ERP\AI_REPORT_INBOX\mpango-mvp-invariants-f1-db-fixture-role-closure-2026-09-08\evidence-root\`
  （env_main/env_weakrun/env_neg.sh、provision_main.sql、provision_negative.sql、
  pg16_bootstrap_demotion_refused.txt、dev_run*.log、dev_mutation_M*.log、gitnexus_impact.txt、
  detect_secrets_run.txt、SHA 清单 manifest.txt）。
- 既有 V3 原始证据（matrix_A.log / preflight.json，V3-R1 报告引用 SHA
  `38a2f193…`/`fcda5d5c…`）：**本 Windows 主机经全盘检索不存在**（检索命令与范围记录于
  evidence-root/prior_v3_evidence_search.txt）；其宿主为 Lubuntu 执行环境。可定位原件：
  git blob `258b98aa:docs/ai-reports/review/mpango-mvp-invariants-r1-r1-f1-client-binding-v3-r1-lubuntu-2026-09-08/review.md`
  与 `findings.csv`（同目录 V3 版本 `4fcaf4de:.../mpango-mvp-invariants-r1-r1-f1-client-binding-v3-lubuntu-2026-09-08/`），
  已在证据根留存脱敏副本与 blob SHA。不以再生成材料替代原件。

## 11. 停止点

NEXT_GATE=KILO_DB_FIXTURE_ROLE_SOURCE_AND_REAL_LIFECYCLE_REVIEW。本轮未修改产品/业务合同、
未合并、未部署、未跑浏览器、未重跑全量后端、未重执行 V3 正式矩阵。新候选改变测试夹具，
Kilo 对旧 SHA 的 PASS 不自动覆盖。

## 12. 完整自查（条目化，PASS / NOT_PROVEN）

> 诚实记录：指令要求"提交前"完成本节；实际产出晚于候选推送（5ac27c74），作为事后补全的
> 修订提交并入。实质核查动作（范围/编码/diff-check/秘密扫描/基线保留/残留/变异恢复）均在
> 提交前执行并散记于 §6/§9；本节将其条目化并补充两项目后核验（blob↔运行字节双哈希、
> 提交后工作树状态）。不以本节冒充"提交前已完成"。

| 维度 | 判定 | 证据位置 |
|---|---|---|
| 修复 1-8 逐一对应真实入口 | PASS | §2/§4/§5；run3/8/10（新文件 10/10、正控单节点、四文件聚焦）；负控 run6/7 |
| 正常对照存在且通过 | PASS | run8 F1 EVIDENCE 两身份行 + 完整生命周期；run10 83 PASS |
| 负面路径不被无关守卫遮蔽 | PASS | 错目标零子进程启动（计数器仅拦 alembic、docker inspect 真跑）；具名分类断言（code 级）；guards 3 反例 |
| 事务与资源：失败回滚/任务终结/零残留/流水不折叠 | PASS | run10 后残留 t_%=0/wholesalers=0/retailers=0；R0 对照节点保持；运行角色零成员实证 |
| 回归证据绑定精确字节 | PASS | §6 run10（最终字节）+ 本节事后双哈希：support blob+CRLF==运行字节（数值一致），guards/新文件 authored-LF（blob(LF)==运行字节，数值一致）；提交恰 4 路径、工作树干净、baseline `f49c8622…` 不变 |
| 范围：无产品/冻结面漂移 | PASS | `git diff 76ab895f` 恰 4 路径；产品/conftest/pw1r3 diff 为空（§1） |
| 发布：diff-check/编码/真实 hook/清单一致 | PASS | §9 + detect_secrets_run.txt（canary rc=1、4 路径 rc=0）；blob UTF-8/无 BOM；提交 stat=4 路径 |
| F1 Redis 51 节点保留 | PASS | collect 前后差集=∅；run5/run10 guards 54/54 |
| 变异语义化且字节恢复 | PASS | §6 M1/M2/M3；恢复 sha256 `66f40141…` |
| 全量后端在角色分离夹具下 | NOT_PROVEN（本轮指令禁止重跑全量；属后续 V3/独立验证） |
| 迁移身份"角色属性级"弱化 | NOT_PROVEN（PG16 结构性禁止降权 bootstrap 超级用户，§7；以只读库载体证同一拒绝链） |
| 正式矩阵 A/B/C | NOT_PROVEN（V3 范畴；本轮明确不重执行） |
| V3 原始 matrix_A.log/preflight.json 字节 | NOT_PROVEN（本机不存在，§10；仅提供 blob 定位与脱敏副本） |
| reporting 身份只读行为 | NOT_PROVEN（011 合同，属其自身套件） |
| Kilo 独立复核 | NOT_PROVEN（NEXT_GATE 本身） |


---

# R1 修复轮（CTO-AUTH-MPANGO-MVP-INVARIANTS-F1-DB-ROLE-R1-COUNTER-REDACTION-2026-09-09）

BASE=`c75d1f7e7aed8617321e233eade8b4884dbd3896`；分支
`zcode/mpango-mvp-invariants-f1-db-fixture-role-closure-r1-2026-09-09`；工作树
`worktrees/zcode_mpango_mvp_invariants_f1_r1_2026-09-09`。实际变更恰两个代码路径
（`git diff --name-only c75d1f7e`：support 与 db_fixture_roles 测试文件；guards 本轮零字节变化，
54 nodeid 平凡保留）；台账本节为第三个提交路径。产品/迁移/角色架构/Redis F1 语义零改动。

## R1-1 两项修复

- **F1 计数器**：`_LaunchCounter._is_migration` 改为类方法，从首个位置参数或 `args=` 关键字
  正确解包 argv；不可分类形态（空/裸串/非列表）一律委托不计——不猜、不吞。四种调用形态单测：
  位置 argv 计 1 且委托 0；`args=` 同；非迁移命令恰委托（docker inspect 形态×2 → delegated=2）；
  畸形×4 全部委托且 launches=0。
- **F1 真实次序**：夹具主体拆为 `_r0_task_database_stages()`（pytest 驱动的同一函数，
  `r0_task_database = pytest.fixture(...)($stages)` 重注册，nodeid/行为不变）。新节点
  `test_f1_wrong_target_refused_before_migration_in_real_fixture_order` 以离线哨兵
  （零 I/O 委托）+ 错库迁移 URL 直驱真实阶段序列：GuardRefused 先于任何迁移启动
  （launches=0；docker inspect 委托可发生=守卫证据）。**计数范围声明**：该零计数仅针对
  本次直驱的阶段序列起点至拒绝，不外推为"整次 pytest 无迁移/无写入"；全文件其余节点的
  session 夹具在测试体之前已按真实次序完成。
- **F2 脱敏**：`_task_known_secrets()` 汇集迁移/运行 URL 口令与 REPORTING_USER_PASSWORD
  的原文及 quote/quote_plus 编码形态；`_sanitize_connection_output` 全部替换 + 既有
  postgres-URL 形状正则。**超时出口同策略**：TimeoutExpired 携带的 stdout/stderr（bytes
  解码）同样脱敏并归入 GUARD_REFUSED_MIGRATION(TIMED OUT)。内容断言套件（3 节点）：
  URL 口令原文+编码形态在 stdout/stderr 双通道均不存在且类别准确；独立 reporting 口令
  （SQL 内嵌形态）不存在；超时分支部分输出脱敏。测试直呼一律移除 MIGRATION_LOG env，
  假结果不污染证据文件。

## R1-2 正控重做（新鲜空库，指令 7）

容器 `mpango-zcode-inv-f1r1-pg`（标签 zcode-mvp-invariants-f1-role-closure）。前态证明：
DROP/CREATE DATABASE 后 `public` 表数=0。夹具以迁移身份真实执行 alembic：证据快照
`r1/migration_output_sanitized_fresh_001_to_037_SNAPSHOT.txt`——恰一块、**37 条
Running upgrade**（链首 `-> 001_initial_schema`、链尾 `036 -> 037_payment_declarations_schema`）、
rc=0、零口令残留（对四项任务口令 grep=0）。随后运行身份完成建租户/读写/清理
（run2/run5：17/17 PASS，F1 EVIDENCE 两身份行），运行后残留 t_%=0、wholesalers=0。
run5 为最终字节绑定运行。不把幂等 no-op 当作完整迁移证据（快照仅取自空库首迁）。

## R1-3 运行记账（原始日志 `evidence-root/r1/`，不覆盖上轮原件）

| # | 范围 | 结果 |
|---|---|---|
| 1 | 新文件（修复后首跑，全新库） | 17 PASS |
| 2 | 新文件（重建空库后，采集干净迁移证据） | 17 PASS；日志恰 1 块 37 升级 rc=0 |
| 3 | guards | 54 PASS（基线 51 差集=0） |
| 4 | 四文件聚焦（中期字节） | 90P+1 已知 RED+2 前提 SKIP |
| 5 | 新文件（最终字节，重建空库） | 17 PASS；快照留存 |
| 6 | 四文件聚焦（最终字节） | **90 PASS + 1 已知双退 RED + 2 缓存前提 SKIP** |

变异（隔离材料 /tmp/f1r1_bak；恢复 sha256：support `f5cf7dec…`、测试 `db899f5b…`）：
MA 恢复旧计数器（argv=args 整体）→ 两计数节点语义 RED（"must count 1, got 0"）；
MB 迁移前置到守卫之前 → 次序节点 RED（"launches=1"）；MC 脱敏器退化为原样返回 →
三个内容断言节点全 RED。恢复后字节一致，17/17 回绿。首次 MA 运行漏 source env
（setup ERROR 非语义），已带 env 重做并如实保留两份记录。

## R1-4 术语与证据边界更正（遵 CTO §3）

- 上轮"弱迁移身份"载体的准确表述：**只读事务/数据库条件拒绝 DDL** 的迁移失败传播证明，
  不是"撤销 CREATEROLE 后仍正确拒绝"的角色属性负控；PG16 禁止降权 bootstrap 超级用户
  （证据保留）。不再尝试属性级复现。
- head==037 不能反推该次执行了全部 001..037；本轮空库前态+37 条升级链+rc=0 快照即为
  该独立证据（Kilo 复核可依同法）。
- run8/run10（上轮）与 run5/run6（本轮）生命周期结论保留为作者开发证据。
- GitNexus：本任务 CLI 索引 impact 记录 0 上游（`r1/gitnexus_r1.txt`）；**CTO MCP compare
  的 4 files/71 symbols/0 processes/low 及 run_public_migrations 3 直接调用者、
  _sanitize_connection_output 4 上游为更完整的真实调用链**，予以采纳，不以前者否定。
  detect-changes：CLI 无该子命令，且本执行会话无 GitNexus MCP 工具面（如实记录），
  以 `git diff --name-only` 唯一路径集 + 暂存逐文件核对替代。

## R1-5 提交前条目化自查（本次实际于提交前完成）

| 项 | 判定 | 证据位置 |
|---|---|---|
| F1 修复：两种合法调用计数=1、委托=0 | PASS | run1/2/5 含 4 计数节点；MA 变异 RED（计数 0≠1） |
| 非迁移命令恰委托一次 | PASS | `test_f1_counter_delegates_non_migration_once`（delegated=2/2） |
| 畸形形态不漏入真实迁移执行 | PASS | `malformed_shapes_delegate_uncounted`（launches=0, delegated=4） |
| 真实夹具次序：守卫先于迁移 | PASS | ordering 节点（launches=0）；MB 变异 RED（launches=1） |
| 计数阶段范围已声明 | PASS | 节点 docstring + R1-1 计数范围声明 |
| 脱敏：三类口令/双通道/超时出口 | PASS | 三个内容断言节点；MC 变异全 RED |
| 超时出口同策略（离线构造） | PASS | timeout 节点（无长耗时进程） |
| 不以测试豁免掩盖实际输出问题 | PASS | pragma 仅用于测试内合成样例字面量；support 实现无豁免 |
| 新鲜空库正控+完整迁移链证据 | PASS | R1-2 快照（0 表前态、37 升级、rc=0、零口令） |
| 既有 guard/F1 语义保留 | PASS | run3 54/54；基线 51 差集=0；本轮 guards 零字节变化 |
| 范围（恰 2 代码路径+台账） | PASS | `changed_paths_r1.txt`；产品面 diff 为空 |
| 真实 hook/diff-check/编码/baseline | PASS | `detect_secrets_r1.txt`（canary rc=1、正式 rc=0、f49c8622 不变）；提交流程核对 |
| 全量后端/正式 V3 | NOT_PROVEN（未授权，未执行） |
| 角色属性级迁移弱化 | NOT_PROVEN（PG16 结构性不可能，术语已更正） |
| Kilo 独立复核 | NOT_PROVEN（NEXT_GATE） |

## R1-6 资源

容器 `mpango-zcode-inv-f1r1-pg`（标签核验）在报告核验后删除；/tmp 变异备份与口令文件已清；
env/regrants/provision 存 `r1/`（合成口令，不入库）；上轮 evidence-root 原件零覆盖。


---

# R2 修复轮（CTO-AUTH-MPANGO-INVARIANTS-F1-DB-ROLE-R2-ENCODED-SECRET-2026-09-09）

BASE=`ae8418d20c65b8eff27b6c0256aa6b668be6d3ed`；分支
`zcode/mpango-mvp-invariants-f1-db-fixture-role-closure-r2-2026-09-09`；工作树
`worktrees/zcode_mpango_mvp_invariants_f1_r2_2026-09-09`。实际变更恰两个代码路径
（`git diff --name-only ae8418d2`：support、db_fixture_roles 测试文件；`changed_paths_r2.txt`）。
产品/迁移/角色供给/Redis 归属规则零改动。唯一阻断项 F2-R1（百分号编码口令不解码）关闭。

## R2-1 修复

- `_add_url_password_forms(url, forms)`（新）：按**实际 URL 口令语义**取集——
  `urlparse().password` 的**原有编码表示**入集；**单次 `unquote` 解码**得到原文入集
  （userinfo 中 `+` 为字面量，故用 `unquote` 而非 `unquote_plus`；无递归解码）；原文的
  `quote(safe='')` 与 `quote_plus` 形态入集。
- `_task_known_secrets(migration_url=None)`：**实际调用参数**的迁移 URL 优先进入集合
  （不只依赖 ambient env），其后三项环境 URL；reporting 口令维持原文/quote/quote_plus。
  口令值仅用于匹配，绝不作为诊断输出（值或哈希均不出现）。
- 三个出口（非零、超时、可选迁移日志）共用 `_sanitize_connection_output` 单一策略；
  类别/rc/非敏感定位保留。

## R2-2 新增节点（+4；文件共 21）

| 节点 | 覆盖 |
|---|---|
| `test_r2_domain_selfcheck_encoded_and_plaintext_are_distinct` | **机器断言**：原文≠URL编码≠quote_plus 形态；`unquote(enc)==原文`；`+` 字面量语义（`unquote('a%2Bb')=='a+b'`、`unquote_plus('a+b')=='a b'`——故解码不用 unquote_plus）；quote 与 quote_plus 对含空格口令形态不同 |
| `test_r2_sanitizer_strips_encoded_password_plaintext_nonzero_exit` | 非零出口：**裸文本解码原文**（CTO 反例形态）+ 完整 URL + 编码 + quote/quote_plus 形态 + 独立 reporting 口令，全部从**拒绝全文**消失；类别保留；非敏感诊断文本（"alembic driver diagnostic"/"connect failed"）保留——非删除充数 |
| `test_r2_sanitizer_strips_plaintext_in_timeout_bytes_output` | 超时出口 **bytes** 部分输出含解码原文 → 全部脱敏、TIMED OUT 类别保留 |
| `test_r2_sanitizer_optional_migration_log_also_sanitized` | 可选迁移日志同一策略：落盘内容零标记且保留 rc 诊断 |

运行/迁移口令分别使用不同合成标记（运行 URL 口令为独立百分号编码值）。

## R2-3 运行记账（原始日志 `evidence-root/r2/`，不覆盖任何历史目录）

| # | 范围 | 结果 |
|---|---|---|
| 1 | 全文件（新容器，run1） | 1 FAILED（domain selfcheck 的 `unquote_plus` 断言写错——%2B 编码下两者本就一致）+20 PASS → 修正断言语义 |
| 2 | 同上 | 同一 selfcheck 再失败（NameError: unquote_plus 缺导入，前次编辑未生效）→ 修正 |
| 3 | 全文件 | **21 PASS** |
| MC2 | 变异：恢复"仅编码、不解码"缺陷 | **三个 R2 语义节点全 RED**（拒绝文本/超时文本/落盘日志各现解码原文泄漏），恢复 sha256 字节一致（support `3e8e97ca…`、测试 `3996d52e…`）→ 21/21 回绿 |
| 4 | 四文件聚焦（R2 字节） | **94 PASS + 1 已知双退 RED + 2 缓存前提 SKIP**；运行后残留 t_%=0、wholesalers=0 |

## R2-4 提交前条目化自查（本次实际于提交前完成）

| 项 | 判定 | 证据位置 |
|---|---|---|
| 解码原文入脱敏集合（缺口本体） | PASS | support `_add_url_password_forms`/`_task_known_secrets`；三个 R2 语义节点 |
| 调用参数迁移 URL 的口令入集（非仅 ambient） | PASS | `_task_known_secrets(migration_url)` 签名+`_sanitize_connection_output` 传参；编码用例自身即以调用参数 URL 承载口令 |
| 输入域真实（机器断言编码≠原文≠quote_plus） | PASS | domain_selfcheck 节点；**MC2 RED 反证域有效性** |
| 全部出口同一策略（非零/超时/日志） | PASS | 三语义节点 + support 三处 `_sanitize_connection_output` 调用点 |
| 类别与非敏感诊断保留（非删除充数） | PASS | 非零出口节点尾断言（"alembic driver diagnostic"/"connect failed" 存活）；日志节点 rc=1 断言 |
| 复用真实实现（无平行复制） | PASS | 全部经真实 `run_public_migrations`/`_sanitize_connection_output`；假子进程结果仅注入数据 |
| 既有回归保留 | PASS | 计数四形态、次序节点、reporting/timeout R1 节点未动（21 含全部）；guards 54/54；聚焦 94P+1RED+2SKIP |
| MC2 敏感性 | PASS | 恢复缺陷 → 三节点 RED；字节恢复 → 21/21 GREEN |
| 范围 | PASS | 恰 2 代码路径（`changed_paths_r2.txt`）；产品/供给/Redis 规则零改动 |
| 秘密扫描/diff-check/编码/baseline | PASS | `detect_secrets_r2.txt`（canary rc=1、正式 rc=0、f49c8622 不变）；提交流程核对 |
| 新节点数量 | 实测 **+4**（文件 17→21）——不预定等于旧数 | run1→run3 计数 |
| 未覆盖 | NOT_PROVEN：全量后端/正式 V3（未授权）；reporting 身份行为（011 合同）；Kilo 复核（NEXT_GATE） |

## R2-5 资源

容器 `mpango-zcode-inv-f1r2-pg`（标签核验）报告核验后删除；/tmp 密钥与备份已清；R0/R1/CTO
诊断/历史 VOID 原件零覆盖；本轮原件存 `evidence-root/r2/`。
