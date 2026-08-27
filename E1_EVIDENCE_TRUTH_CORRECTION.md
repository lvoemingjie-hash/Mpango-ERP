# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-V2-E1 — Preflight Evidence-Truth Correction

- 日期：2026-08-27（+08:00）；执行者：opencode（Lubuntu 宿主）
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-V2-E1
- VERIFICATION_TIER: V0_EVIDENCE_CORRECTION_ONLY
- CLAIM_CEILING: EVIDENCE_TRUTH_CLOSURE_ONLY
- CANDIDATE: `bf20e8c9eae620fcf101ded672dfb0afeab937cb`（未变）
- KILO_REVIEW: `f5fdf187fab88f628a6b2f3aca80d03d3be60054`（未变）
- PROTECTED_BASELINE: `2c20d58c88a0a8f5175f4d11041d03b6ca785e06`（未变）
- 原 V2 checkpoint：分支
  `reports/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-v2-lubuntu-independent-backend-final-2026-08-27`
  tip `013d765a0087ca7a96d0b4e7d9f812c9a36949aa`（父提交 = CANDIDATE，
  已推送，未重写）
- 本 E1 提交：上述 checkpoint 的线性 fast-forward 子提交

## 1. 裁决修正（Phase 2 — Required Truth Corrections）

RUN_VERDICT:
**VOID_ENVIRONMENT_PRECHECK**

OVERALL_TASK_STATUS:
**STOP_AND_REPORT_CTO_WITH_VOID_ENVIRONMENT_PRECHECK**

FULL_SUITE_CLASSIFICATION:
**VOID_ENVIRONMENT_PRECHECK**

### PREVIOUS_WORDING_WITHDRAWN（撤回以下原始措辞）

1. "Phase 2 Preflight: 基本通过" — 撤回。preflight 合同不完整：未验证
   `MPANGO_ALLOW_TEMP_DB_CREATE` 精确等于 `"1"`，遗漏了任务数据库
   temp-DB 能力前提。
2. "权威全量运行" / "权威运行完成" — 撤回。该 invocation 因环境 precheck
   缺陷不具备权威效力。
3. 任何将 42 个红节点归为候选测试失败的措辞 — 撤回。42 个红节点
   （13 failed + 29 errors）全部属于 temp-DB/Alembic 证据家族
   （s4g migration infra、i1_r4_r1 real-alembic、dc11t2 temp-db、
   dc11t4c、s1_r5 preflight），是缺失能力变量触发的 fail-closed
   安全门按合同生效，**不是产品缺陷，不是候选缺陷，不是候选测试失败**。

### EXACT_CAUSE

**PRECHECK_CONTRACT_OMITTED_REQUIRED_TEMP_DATABASE_CAPABILITY**

具体事实（如实记录）：

1. `MPANGO_ALLOW_TEMP_DB_CREATE` 未被验证为精确值 `"1"`（发射前根本
   未设置该变量）。
2. pytest 因缺失该能力变量触发 temp-DB/Alembic fail-closed 安全门：
   - 29 errors：setup 断言 `MPANGO_ALLOW_TEMP_DB_CREATE=1 required for
     real Alembic evidence tests`（assert None == '1'）。
   - 13 failed：`RuntimeError: temporary database creation requires
     explicit opt-in` / `temporary database source must have an explicit
     test name`。
3. 13 failed + 29 errors = 42 个红节点均属于该 temp-DB 家族，与 R1
   ledger 记录的 Windows 红集家族 1:1 对应。
4. 该 full-suite invocation **不具备产品裁决效力**：不构成 backend
   zero-red，也不构成 candidate red。
5. 未授权重跑，未发生刷绿。完成的 invocation 原始字节原样归档于
   checkpoint `evidence/fullsuite-authoritative.{log,xml}`，未删除、
   未重写、未伪造。

## 2. Valid Evidence Retained（Phase 3 — 与作废 full-suite 分开记账）

以下证据继续有效（均产生于 precheck 缺陷影响面之外——focused 运行
不依赖 temp-DB 能力）：

| 证据 | 结果 |
|---|---|
| FW3 单节点 | 1/1 GREEN |
| FW1–FW5 | 5/5 GREEN |
| H2-C 模块自然序 | 11/11 GREEN |
| H2-C 模块反向序 | 11/11 GREEN |
| H2-C 同进程双轮 | 11/11 + 11/11 GREEN |
| focused bundle 精确收集 | 49 |
| focused bundle 自然序 | 49/49 GREEN |
| focused bundle 反向序（文件倒序） | 49/49 GREEN |
| 候选 tree/hash | 未漂移（tree `86eead40…` 前后一致；test 模块 SHA-256 `39e451c0…` 与 R2-R1 ledger 逐位一致） |
| H2-C 任务自有残留 | 精确身份/schema/token/DB15 全零 |
| 静态质量门 | py_compile / diff --check / UTF-8-no-BOM-no-NUL-LF 全过 |

**边界声明**：不得把这些 focused 结果提升为 full-backend PASS。

## 3. Process Disclosure（Phase 4 — 如实保留）

1. 三次 VOID 发射及各自原因（均未计入权威产品运行）：
   - 发射 1：-v 前台，30 分钟工具超时被杀 — 未完成。
   - 发射 2：-q 前台，用户中止 — 未完成。
   - 发射 3：nohup 未脱离进程组，90 秒后轮询命令超时 SIGKILL 连坐杀死
     进程组 — 未完成（原始 log 字节归档于本 E1 提交 evidence/
     VOID-fullsuite-launch3-killed-infrastructure.log；checkpoint 因
     .gitignore `*.log` 规则仅纳入 9/12 证据文件，本 E1 以未修改原始
     字节补录 3 个 console log，见 §5 披露）。
2. 没有任何一次 VOID 发射被计入权威产品运行；唯一完成的发射
   （发射 4，26:08）即被 E1 分类为 VOID_ENVIRONMENT_PRECHECK 的对象。
3. 中途 CTO amendment 已将任务顺序改为
   `preflight → 49-test 双序 → HC01–HC17 浏览器 → 最终候选冻结 → 一次完整 backend zero-red`，
   且明确"当前先不要执行完整 backend suite"。
4. 旧 Phase 4（销毁重建后立即全量）不应继续执行，但执行方沿旧任务书
   启动了 full suite — 流程偏差，如实记录，不辩解。
5. 后续任务变更必须有 TASK_AMENDMENT_ACK 后方可继续（本 E1 即对该
   amendment 的追溯确认与证据收口）。

## 4. Future Preflight Requirement（Phase 5 — 仅记录，不执行）

1. 必须验证 `MPANGO_ALLOW_TEMP_DB_CREATE == "1"`（精确值，不是只检查
   变量存在）。
2. pytest 收集前必须实际完成一次任务数据库的 create/drop smoke proof。
3. 上述任一失败必须在 collection 前退出并标记
   `VOID_ENVIRONMENT_PRECHECK`。
4. 浏览器候选最终冻结前不再执行 full backend suite。

## 5. Evidence Integrity（Phase 6 — 执行记录）

1. `/tmp/dc12r1-v2-evidence/` 原始证据文件保持字节不变（本 E1 未触碰；
   逐一 SHA-256 与运行当日记录一致）。
2. 本 E1 分支的变更文件恰为：
   - `report.md`（仅 verdict/分类措辞修正）
   - `findings.csv`（仅对应分类列修正）
   - `E1_EVIDENCE_TRUTH_CORRECTION.md`（本文件，新增）
   - `manifest-sha256-e1.txt`（从 committed git blob 原始字节重算，新增）
   - 补录 3 个原始 console log（`evidence/fullsuite-authoritative.log`、
     `evidence/fullsuite-launcher.log`、
     `evidence/VOID-fullsuite-launch3-killed-infrastructure.log`）：
     checkpoint 提交时仓库 `.gitignore:23`（`*.log`）静默排除了它们，
     导致 checkpoint 仅含 9/12 证据文件且本文件 §3 引用缺失——为保持
     "3 次 VOID 发射有原始字节档案"的过程披露真实性，以未修改原始
     字节补录（SHA-256 与 checkpoint 当日 /tmp 记录逐一相等：
     `21ffdc99…` / `f07b3c14…` / `23135f6c…`）。不重写 checkpoint
     历史；已入库的 9 个证据 blob 自 checkpoint 起零变化。

   **发布过程披露**：E1 首提交 `d2ca55fb5aa96a9e32883fe4279e41b0687405ca`
   发布不完整（仅纳入 3 个 log 与 manifest，遗漏 report.md/findings.csv
   措辞修正与本文件）。因禁止 force-push，以本线性后继补全提交
   （即本分支 tip）完成全部变更；首提交保留为不可变历史，不重写。
3. manifest 对账结果（提交后自 git blob 重算）：missing=0 / extra=0 /
   mismatch=0。
4. 原始 JSON/JUnit/console/preflight 证据 blob 不变证明：12/12 文件的
   E1-tree blob SHA-256 == /tmp 原始字节 SHA-256；9 个 checkpoint 内
   文件另证 blob == checkpoint blob。
5. 严格 UTF-8 / no-BOM / no-NUL / LF：本提交全部新增/修改文件通过。

## 6. 裁决

FINAL VERDICT:
**PASS_FOR_CTO_DC12R1-MVP_L1_J1_H2_C_R1_R2_R1_V2_E1_PREFLIGHT_EVIDENCE_TRUTH_CLOSURE**

推送并证明 local == remote 后 STOP。不启动 Zcode、harness、浏览器、
全量后端、合并或部署。
