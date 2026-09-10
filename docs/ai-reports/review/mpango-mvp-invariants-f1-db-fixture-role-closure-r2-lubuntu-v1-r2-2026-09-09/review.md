# Lubuntu V1-R2 独立验证 review — MPANGO-MVP-INVARIANTS-F1-DB-FIXTURE-ROLE-CLOSURE-R2

- 日期：2026-09-09/10
- 授权：`CTO-AUTH-MPANGO-F1-DB-ROLE-R2-LUBUNTU-V1-R2-2026-09-09`
- 执行者：**Claude Code on Lubuntu**（ivy-20149）
- 报告 parent == 候选 `e0a6363958142ecfbfc48f68cce73fb3a6c32349`（Git commit object ID）；候选零写入
- 验证层级：V3_MERGE_CRITICAL；声明上限：LUBUNTU_CURRENT_CANDIDATE_REAL_PG_FIXTURE_LIFECYCLE_ONLY

## 裁决

```text
STOP_AND_REPORT_CTO
R2_DISPOSITION=TEST_ERROR (fixture migration subprocess stage, pre-write)
R2_FORMAL_PYTEST_INVOCATIONS=1 (counted before launch; not zeroed)
R2_TEST_BODIES_EXECUTED=0
R2_MIGRATION_EXECUTED=ATTEMPTED_FAILED_PRE_WRITE
PRODUCT_VERDICT=NOT_EVALUATED_TO_COMPLETION
LUBUNTU_MUTATION=NOT_RUN_THIS_ROUND
```

正式 pytest rc=1：会话首节点 `test_f1_positive_role_separated_full_lifecycle` **setup ERROR**。夹具进入迁移阶段并真实启动 alembic 子进程（迁移身份、显式迁移 URL），子进程在 `alembic/env.py:38` 失败：configparser BasicInterpolation 拒绝 URL 中的 `%`（本轮迁移密码为 `%23` 编码形态）。失败早于引擎连接：0 条 Running upgrade，结束时 public 表=0、alembic_version 缺席、t_%=0（只读核验）。

**证据链事实（定性归 CTO）**：候选 R2 设计以百分号编码密码为一等公民；候选未改动的产品 env.py 经 configparser 传 URL，排斥任何含 `%` 的密码编码形态。候选测试声明与产品迁移路径的不兼容 vs 执行者密码形态选择——证据完整呈交，不自行定性。守卫脱敏全链正确（全部错误出口密码位 `***`；执行者独立扫描 CLEAN）。

## 制度修正验证（R2 新增）

V1-R1 的 precheck harness 缺陷制度修正**有效**：完整预检重写为单进程 Python，离线 41/41 样本（docker 正负控、R1 回归、PG 负控、汇总/泄漏负控）后，真实预检**一次调用 26/26 全绿 rc=0**。R1 类失败未再发生。

## 独立证据（本轮真实执行）

证据根：`/home/ivy/AI_REPORT_INBOX/mpango-mvp-invariants-f1-db-fixture-role-closure-r2-lubuntu-v1-r2-2026-09-09/`；STOP_RECORD.md 与 31 文件 SHA-256 索引见 findings.csv 与任务根 `logs/sha_index_final.log`（64 位=SHA-256，40 位=Git object ID，分栏不混称）。

| 门 | 结果 | 证据 |
|---|---|---|
| P0 SHA/parent/路径/旧 STOP/原件交付复核 | PASS | `logs/p0_proof.log` |
| P1 离线样本矩阵 41/41（含 R1 回归、泄漏负控） | PASS rc=0 | `logs/offline_selftest_r2.log` |
| P1 PREPARATION_RED=5（全部记录修复） | recorded | `logs/preparation_record.md` |
| 冻结门 OFFLINE_PREFLIGHT_QUALIFIED=true + 脚本逐文件 SHA | DONE | `logs/freeze_manifest.md`, `logs/script_sha_index.log` |
| P2 config check rc=0 + collect 21 节点 + 静态门 | PASS | `logs/config_check_p2_r2.json`, `logs/collect_*`, `logs/static_gates_r2.log` |
| P3 供给一次 rc=0（唯一栈，三身份） | PASS | `logs/provision_r2.log` |
| P3 真实预检一次 26/26 rc=0（计数 0→1 先于调用） | PASS | `logs/runtime_preflight_r2.json`, `logs/preflight_counter.log` |
| P4 正式 pytest（计数 0→1 先于启动） | **rc=1 TEST_ERROR** | `logs/formal_invocation_r2.log`, `evidence_redacted/pytest_formal_r2.log`, `evidence_redacted/junit_r2.xml`, `evidence_redacted/migration_log_r2.txt` |
| 库态终态只读核验（零写入确认） | DONE | `logs/db_final_state_r2.log` |
| 清理（容器/卷/端口/凭据/worktree；既有 9 容器零接触） | DONE | `logs/cleanup_r2.log`, `logs/docker_ps_after_cleanup_r2.log` |

## 环境声明一致性（公开布尔值）

三 URL scheme=postgresql:// TRUE；TEST==DATABASE 字节相同 TRUE；迁移同库不同用户 TRUE；owner 前缀 TRUE；SECRET_KEY/REPORTING_USER_PASSWORD/loopback REDIS_URL 显式独立 TRUE；私有 env 0600、原字节一致性私有核验 TRUE。密码含 `%23` 编码形态（授权占位 `<encoded-password>` 形式）——此选择与失败的因果关系见裁决节，呈 CTO 定性。

## 计数（V1→V1-R1→V1-R2 链）

formal OS attempts：1+0+1=**累计 2**；test bodies 累计 0；collect 3；config checks R1=2/R2=2；离线自测 6（5 PREPARATION_RED+1 PASS）；供给 3 轮各 1 次 rc=0；真实预检 R1=1(rc=1)/R2=1(rc=0)。

## 未覆盖项

21 节点测试体、37 条 Running upgrade、运行身份生命周期、负控真实顺序、R2 三脱敏出口真实运行（全部因首节点 setup ERROR 未达）；变异（授权内 NOT_RUN）；guards 全量/四文件矩阵/全量后端/Redis/浏览器（范围外）。

## 先验证据（仅关联）

V1/R1 轮 Lubuntu 证据（候选字节未变）；Kilo `22ba1059…`（Git object ID）PASS；作者提交声明（21/21、MC2 恢复）——均未由本轮复现。GitNexus 旧索引按候选 SHA 关联，标先验。

## 披露

- 本轮**零泄漏**（全 artifacts 三密码 raw/quote/quote_plus+SECRET_KEY 扫描 CLEAN；预检改 allowlist 输出，无 R1 式 inspect 事件）。
- R1 泄漏传播：仅限本机任务根，未推送未外发，口令随 R1 资源销毁失效；不可知副本：未知（如实）。
- 权限变更：用户授权后向项目 settings.local.json 添加三条本轮脚本精确路径 Bash 规则（用户另自行添加 `Bash(python3 *)`）；全部拦截/授权事件记录于任务根 `logs/permission_decisions.md`。

## 已知产品 RED 保留

重复退货 RED、缓存隔离 RED/SKIP 继续登记；本轮 21 节点未通过，**不**构成任何放行结论；即便未来某轮 21 PASS 也不得外推为全产品零红。
