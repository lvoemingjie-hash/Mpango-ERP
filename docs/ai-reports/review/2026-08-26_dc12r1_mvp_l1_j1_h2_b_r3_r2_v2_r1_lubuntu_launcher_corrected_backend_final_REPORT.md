# DC-12R1-MVP-L1-J1-H2-B-R3-R2-V2-R1 — LUBUNTU Launcher-Corrected Single Authoritative Backend Final

- **日期:** 2026-08-26（+08:00）
- **执行方:** OpenCode — Lubuntu 原生独立主机
- **风险等级:** V3_MERGE_CRITICAL；CHANGE_CLASS: EXECUTOR_ENVIRONMENT_CORRECTION_ONLY
- **CLAIM_CEILING:** INDEPENDENT_BACKEND_GATE_PASS（非 browser PASS、非 merge/release approval）
- **模式:** V2 STOP（VOID_EXECUTOR_LAUNCHER_ENVIRONMENT）的授权修正轮。单次 fresh-runtime 权威后端全量；未合并、未部署、未启动 H2-C、未运行 Playwright。

## 最终裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R3_R2_V2_R1_LUBUNTU_INDEPENDENT_BACKEND_FINAL
```

即使 PASS 也按指令 STOP：不运行 Playwright、不合并、不部署、不启动 H2-C。

## Phase 1 — 证明门（全 PASS）

candidate `25626f4d` == 远端 tip ✓；KILO_REVIEW `d6289a6b` 存在且父 == candidate ✓；V2 证据分支 tip == `88ba0d56` 未重写/未 force-push ✓（V2 分类固定为 VOID_EXECUTOR_LAUNCHER_ENVIRONMENT）；protected `6e9470a1` 不变 ✓；detached clean checkout at candidate，树与 V2 执行候选字节一致 ✓。

## Phase 2 — 全新权威栈（全 PASS；零 V2 复用）

新容器名 `r3r2r1-pg`/`r3r2r1-redis`、网络 `r3r2r1-net`、卷 `r3r2r1-{pgdata,redisdata}`、库 `test_r3r2r1_auth`、端口 127.0.0.1:15603/16603——与 V2 的栈（15602/16602）完全不同；PG16 非超级用户 r3r2tester（CREATEDB）+ **max_connections=300 实证**；Redis DB0/DB15 初始均空（FLUSHALL 后 dbsize=0/0）；Alembic 37 迁移 → 唯一 head `037_payment_declarations_schema`；127.0.0.1:26379 全程 connect_ex=111 无监听。

## Phase 3/4 — Launcher 修正与过程边界证明（全 PASS）

任务私有 `run_authoritative.sh`（不入产品分支）：先在自身进程构造并导出 DATABASE_URL，随后执行指令规定的修正序列 `: "${DATABASE_URL:?}"` → `export TEST_DATABASE_URL="${DATABASE_URL}"` → `: "${TEST_DATABASE_URL:?}"`。

**双份脱敏证明同时全 TRUE：**
- `launcher_env_proof_pre_exec.json`（runner shell 内、pytest 前）：set/nonempty/equals_DATABASE_URL/expected_host(127.0.0.1)/expected_port(15603)/expected_database(test_r3r2r1_auth)/Redis 端口一致/26379 不在任何 URL。
- `launcher_env_proof_pytest_session.json`（由 pytest 进程自身经任务私有 `-p` 插件在 `pytest_sessionstart` 写入，pid 在案）：同一组检查全部 true——证明 pytest 继承的就是 runner 的同一环境，非仅 shell 父进程。

**负控证据**：毒化副本（错误栈端口 99999）→ 探针拒绝 → `VOID_ENVIRONMENT_PRECHECK` rc=9，收集前退出。披露：更早一次负控尝试误启动真实收集（~2% 执行），已即时终止并将权威栈销毁重建为全新卷后才执行唯一权威运行。

## Phase 5 — 唯一权威运行（字面零红）

V2 已通过的 9/9、97/97、pw1r3 7/7 预检保持有效未重复。单次调用（exec 继承同一环境），1704.70s（0:28:24）：

| 口径 | collected | passed | failed | errors | skipped | xfailed | xpassed | gap |
|---|---|---|---|---|---|---|---|---|
| 期望 | 3773 | 3710 | 0 | 0 | 48 | 15 | 0 | 0 |
| **实测** | **3773** | **3710** | **0** | **0** | **48** | **15** | **0** | **0** |

**EXACT_ALL_AXES**。运行前复证 DB0/DB15 空、037 head、26379 无监听、最终 LF 字节 SHA-256（test 文件 `00c64a89…`、crud/user.py `95c89cbd…`）与作者台账逐字节一致。

## Phase 6 — Post-Run Truth（fresh admin connection）

**wholesalers=4 / tenant_registrations=0 / UUID schemas=29 —— 与已知候选终态 4/0/29 完全一致。**
标记 `PRE_EXISTING_OUT_OF_SCOPE_TEST_HYGIENE_DEBT`；不声称 residue=0；未以模块重放改写权威结果。（披露：首次快照探针长度过滤有误[33 vs 34]报出 0，只读复核修正为正则 `^t_[0-9a-f]{32}$`=29。）无临时数据库残留（extra_databases=0）、dc11t2fr_% 角色=0、Redis DB0=3 键/DB15=0。

## Phase 7 — Evidence（本分支 evidence 目录）

REPORT.md、preflight.json、launcher_env_proof_{pre_exec,pytest_session}.json、run_authoritative_sanitized.sh（PG_PW 值已 REDACTED）、raw console.log + full_junit.xml（零红无需消毒，扫描确认零秘密）、reconciliation.json、skip_nodes.txt（48）/xfail_nodes.txt（15）、post_run_residue.txt、cleanup closure、committed-blob SHA-256 manifest。不含 URL 凭据/密码/JWT/SECRET_KEY/原始 environ dump。

## Quality（Phase 内含）

py_compile OK；git diff --check OK；scoped pre-commit 全 Passed exit 0（hook 未改动任何文件）；detect-secrets 4 文件 0 findings；UTF-8/no-BOM/LF-only 4/4；GitNexus analyze（34,422 nodes/56,854 edges/752 clusters）+ status 钉住 `25626f4` ✅；refs 终验不变。

## Phase 8 — Cleanup（cleanup.md）

容器/卷/网络删除、四端口释放、凭据 shred、worktree 移除、冻结 refs（candidate/Kilo/V2/protected）终验不变。

## 裁决链

本 PASS 覆盖 V2 的 VOID（执行方环境缺陷）。CLAIM_CEILING 为 INDEPENDENT_BACKEND_GATE_PASS——browser 门禁、merge review、release approval 均不在本裁决范围。
