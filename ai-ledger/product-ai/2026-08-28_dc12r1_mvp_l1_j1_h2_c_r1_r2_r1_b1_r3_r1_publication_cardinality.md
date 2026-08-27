# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R3-R1 — Publication Ordering & Setup Cardinality Closure

- 日期：2026-08-28（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R3-R1（Reconciliation Publication
  Ordering and Setup Cardinality Closure）
- 验证层级：V1_HARNESS_SOURCE_AND_EXECUTABLE_CONTRACT；CLAIM_CEILING：
  `HARNESS_CORRECTION_CANDIDATE_READY_FOR_KILO_RE_REVIEW_ONLY`
- BASE：`d11b51045fe415e5b8e3222e7bc037af75138c92`（B1-R3 tip，远端一致）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-b1-r3-r1-publication-cardinality-closure-2026-08-28`
- 授权范围：恰 4 个 harness 文件 + 本台账；未修改产品/产品测试/依赖/
  lockfile/其他 harness；未启动产品运行时/PG/Redis/Vite/Playwright 旅程。
- GitNexus 编辑前 impact：`publishArtifacts`/`assertComplete`/setup 基数
  调用方全部闭合于 harness 内部（spec/validator/fixtures/scanner）；
  无 HIGH/CRITICAL（记录后继续）。

## 1. 修正一：先发布，再判定成功完整性

afterAll 重写为三路真值顺序：

1. **PRECONDITION_FAIL**：`recordPreconditionFail` 已保留 17 NOT_RUN；
   仅发布 reconciliation，不追加任何虚构节点失败。
2. **浏览器节点失败**：先 `markOutcomesAfterFailure(firstFailedNodeId)`
   精确分类 PASS/FAIL/NOT_RUN，再发布——新的完整性异常不可能在发布
   前抛出，首败不被覆盖。
3. **表面成功**：先 `publishArtifacts`（真实状态，可能含 PENDING），
   **再** `assertComplete()`。漏记任一节点时同时满足：
   - reconciliation.json/csv 已发布且含真实 PENDING/非完整状态
     （fixture 断言 HC17=PENDING 已落盘）；
   - assertComplete 抛出（teardown error → Playwright 非零退出）
     （fixture 断言 throw）；
   - 绝不出现"只 RED 而缺 reconciliation 工件"。
4. `clearMemoryState()` 始终位于 finally。

## 2. 修正二：setup token 基数严格等于 1

scanner 对 established 与 unverified 两个 mailbox 分别要求
`setupTokens[label].length === 1`：**零个或多于一个均 fail closed**
（`setup_token_cardinality:<label>:<count>`，仅 label+category，无值）。
reset token 不限数量——全部收集、全部扫描（既有 fixture 保持）。

## 3. 真实性门 M32–M35（RED → SHA-256 恢复 → GREEN）

| Mutation | 内容 | RED | 恢复 |
|---|---|---|---|
| M32 | 交换为 assertComplete 先于 publishArtifacts | ✓（ordering fixture） | SHA-256 一致 |
| M33 | 漏记 HC16 变体（删成功路径 assertComplete） | ✓（M33 fixture：发布真实 PENDING + 判定 throw） | SHA-256 一致 |
| M34 | unverified mailbox 两个不同 setup tokens 被容忍 | ✓（M34 fixture） | SHA-256 一致 |
| M35 | established 基数守卫被删 | ✓（M35 fixture） | SHA-256 一致 |

如实记录：M35 首轮 ANCHOR-MISSING 为变异锚缩进与源不一致（变异脚本
问题，非候选缺陷）；以正确缩进复验为确定性 RED。零 setup token 的
fail-closed（`setup_token_cardinality:unverified:0`）亦由 fixture 证明。

每项恢复后：候选文件 bytes 与 SHA-256 逐位一致；validate-static GREEN；
check-runtime-contracts GREEN。

## 4. 冻结门禁（全部通过）

`pnpm install --frozen-lockfile`；`--list` 15 tests / 1 spec / 有序一致；
validate-static 11/11；check-neutrality G1–G6；check-runtime-contracts
（含 B1-R3-R1 ordering/cardinality）；`tsc --noEmit`；`git diff --check`；
baseline detect-secrets PASS；全文件严格 UTF-8/no-BOM/no-NUL/LF；
GitNexus impact（编辑前）+ detect_changes（提交前，变更仅限授权文件）
+ commit 后 analyze/status pinned；local == remote（推送后验证）。

## 5. 裁决

FINAL:
**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_R2_R1_B1_R3_R1_CANDIDATE_READY_FOR_KILO_RE_REVIEW**

CLAIM_CEILING：`HARNESS_CORRECTION_CANDIDATE_READY_FOR_KILO_RE_REVIEW_ONLY`。
完成后 STOP：不启动 Kilo、不运行浏览器、不合并、不部署。
