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
