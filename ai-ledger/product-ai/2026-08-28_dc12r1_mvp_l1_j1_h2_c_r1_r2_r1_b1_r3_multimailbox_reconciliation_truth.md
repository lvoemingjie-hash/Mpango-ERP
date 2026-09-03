# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R3 — Multi-Mailbox Scanner & Reconciliation Truth Closure

- 日期：2026-08-28（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R3（Multi-Mailbox Scanner and
  Reconciliation Truth Closure）
- 验证层级：V1_HARNESS_SOURCE_AND_EXECUTABLE_CONTRACT；CLAIM_CEILING：
  `HARNESS_CORRECTION_CANDIDATE_READY_FOR_KILO_RE_REVIEW_ONLY`
- BASE：`00934b733ee62552933261b0b913a3ead96117d1`（B1-R2 tip，远端一致）
- 只读 refs：PRODUCT_SOURCE `bf20e8c9…`、PRIOR_KILO_STOP `26ed3fac…`、
  受保护基线 `2c20d58c…` —— 全部未漂移。
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-b1-r3-multimailbox-scanner-reconciliation-truth-2026-08-28`
- 授权范围：`j1h2c-retailer-recovery/**` + 本台账；未启动产品运行时/
  PG/Redis/Vite/Playwright 旅程；未改产品源码/产品测试/j1h2b/依赖/锁文件。

## 1. 编辑前门禁

- fetch --all --prune；BASE 与远端 tip 一致；独立 clean worktree。
- GitNexus upstream impact（`runPreconditions`、`markOutcomesAfterFailure`、
  scanner 入口）：全部调用方均在 harness 内部（spec/validator/runtime
  fixtures/scanner 自身）；零外部依赖方。无 HIGH/CRITICAL —— 记录风险
  （仅 harness 内部符号，变更影响闭合于本目录）后继续。

## 2. 多邮箱扫描缺口闭合

- **双邮箱快照**：`runPreconditions` 在任何注册副作用**前**同时快照
  established 与 unverified 两个 mailbox；artifact 升级为
  `j1h2c-maildir-snapshot/2`，仅保存稳定身份标签（established/unverified）
  与文件名集合——不含邮箱、token、URL 或任何值（validator
  `-absent-snapshot` 禁令强制：snapshot 写入块内不得出现
  `normalizeEmail(env.retailer.email)` / `normalizeEmail(env.unverifiedEmail)`）。
- **scanner 双邮箱派生**：从 env 读取两邮箱（值仅存内存）；仅扫描
  snapshot 差集内本次新邮件；收集并扫描：established setup token、
  unverified setup token、established 全部 reset tokens、HC15 forged
  token（fixture 证明 4 项 secret 全部入集）。
- **fail-closed 集**：任一预期 mailbox snapshot 缺失、目录不可读、
  任一 mailbox 无新 setup token、token 跨邮箱重复、forged 与任一真实
  token 相同、动态 env 缺失——全部 RED（只含 label/surface/category，
  不输出邮箱/文件名/秘密值）。
- **历史排除**：两邮箱的历史邮件均被 snapshot 排除（fixture 用两个
  历史 token 泄漏文件证明不触发）。

## 3. Reconciliation 误分类闭合

- 四态明确：`PRECONDITION_FAIL`（顶层，独立字段，绝不伪造到 HC 节点）、
  节点 `PASS` / `FAIL` / `NOT_RUN`。
- **beforeAll 失败**：`recordPreconditionFail()` —— precondition=FAIL、
  15 browser + 2 static 全部 NOT_RUN、零伪造节点 FAIL；真实 artifact
  先发布再 rethrow（fixture：fail=0 / notRun=17 / pending=0 / pass=0）。
- **浏览器节点失败**：`markOutcomesAfterFailure(firstFailedNodeId)` +
  afterEach 首败捕获——精确失败节点=FAIL、已完成节点维持 PASS、后续
  节点=NOT_RUN；HC11/HC17 按真实 HC07 依赖记账（HC07 未达即 NOT_RUN）
  （fixture：HC03 首败 → pass=2/fail=1/notRun=14，逐节点断言）。
- **全成功**：afterAll（仅当无首败且 precondition 通过时）执行
  `assertComplete()`——15 browser PASS + 2 static PASS、0 FAIL / 0
  NOT_RUN / 0 PENDING；**漏掉任一 record 必使命令 RED**（M30：漏
  HC16 → throw → teardown error → 非零退出），不会静默产出不完整
  JSON 后 exit 0。
- reconciliation 仍先发布真实状态；清理/发布异常独立 surface，不静默
  掩盖原始首败（finally 中 clearMemoryState 保持）。

## 4. 强制真实性测试（M28–M31 全 RED → SHA-256 恢复 → GREEN）

| Mutation | 内容 | RED | 恢复 |
|---|---|---|---|
| M28 | 删除 unverified mailbox 扫描 | ✓（unverified setup token 泄漏被 fixture 抓住） | SHA-256 一致 |
| M29 | beforeAll 失败恢复为"全部 FAIL" | ✓（17 NOT_RUN 断言失败） | SHA-256 一致 |
| M30 | 删除成功路径 assertComplete | ✓（漏记 HC16 变体 RED） | SHA-256 一致 |
| M31 | snapshot 写入邮箱值 | ✓（validator 禁令 + fixture 双路径） | SHA-256 一致 |

如实记录：M31 首轮 NOT-RED 根因是 fixture 只检查自建 fixture 文件而
未触及模块 snapshot 写入块——已以 validator `-absent-snapshot` 禁令
（写入块内禁止出现 email 规范化值）+ M31/M31b 双变体复验为确定性 RED。

同时证明：两邮箱历史邮件排除 ✓、两邮箱 setup token 入集 ✓、reset 与
forged 泄漏均被发现 ✓、beforeAll 失败对账 precondition FAIL + 17
NOT_RUN ✓、HC03 首败精确 ✓、完整成功 17/17 gap=0 ✓、每 mutation 恢复
后 blob SHA-256 逐位一致 ✓。

## 5. 冻结门禁（全部通过）

`pnpm install --frozen-lockfile`；`--list` 15 tests / 1 spec / 有序不变；
validate-static 11/11；check-neutrality G1–G6；check-runtime-contracts
（A/B/E/C/H/I + B1-R3 多邮箱/对账真相）；`tsc --noEmit`；
`git diff --check`；baseline-mode detect-secrets PASS；全文件严格
UTF-8/no-BOM/no-NUL/LF；GitNexus detect_changes（提交前，变更仅限
harness 授权文件）+ commit 后 analyze/status pinned；产品/j1h2b/backend
tests 相对 PRODUCT_SOURCE 零变化；变异后 tree 无漂移（status clean）。

## 6. 裁决

FINAL:
**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_R2_R1_B1_R3_CANDIDATE_READY_FOR_KILO_RE_REVIEW**

CLAIM_CEILING：`HARNESS_CORRECTION_CANDIDATE_READY_FOR_KILO_RE_REVIEW_ONLY`。
推送、local == remote、worktree clean。STOP：不启动 Kilo、不运行浏览器
旅程、不合并、不部署。
