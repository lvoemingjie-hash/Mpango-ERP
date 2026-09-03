# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R5-R4 — Single Canonical Repository Identity (Cross-Repo Candidate Substitution Closure)

- 日期：2026-08-31（+08:00）；执行者：Zcode
- BASE：`18d71fd1bb85367c03d404774f788f5b71a4a731`（B1-R5-R3 候选；候选与远端
  引用未修改）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r5-r4-canonical-repo-identity-2026-08-31`
- 验证层级：`V1_BOUNDED_SOURCE_AND_TEST_AUTHENTICITY`
- 声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`
- 输入：CTO 裁决 `NEED_CHANGES_BEFORE_KILO_REVIEW`（P1 跨仓库 candidate 替换：
  profile committed blob 经 profile 自身仓库验证，candidate SHA 却经调用方
  独立 `repoRoot` 验证，二者从未证明同仓；反例 foreign repoRoot →
  accepted=true/boundToForeign=true/category=null）

## 1. 修复

1. **唯一 canonical repository root**：新增 `canonicalRepoRoot(profilePath)`，
   从模块/profile 自身位置派生 `git rev-parse --show-toplevel`（env 消毒后的
   argv 数组 subprocess）。profile committed-blob 证明与 candidate HEAD 解析
   **共用同一 toplevel**。
2. **调用方 repoRoot 收紧**：参数保留但必须 `realpath` 精确等于 canonical
   root（Windows 大小写不敏感比较）；否则构造器即抛
   **`repo_root_mismatch`**（fail fast，未构造即无启动）；通过后 `#repoRoot`
   一律改存 canonical 值。
3. **GIT_* 环境消毒**：新增 `gitEnv()`，所有 git subprocess（show-toplevel/
   cat-file/rev-parse）以剥离全部 `GIT_*` 变量的环境运行——`GIT_DIR`/
   `GIT_WORK_TREE`/`GIT_INDEX_FILE` 等仓库劫持注入不再可能改变 profile/
   candidate 仓库身份。

## 2. Delta（恰为 4 文件 + 本台账）

runner（修改）、checker（修改）、validate-static（修改，[14] 锚点扩展）、
README（修改，R4 小节）、本台账（新增）。其余一切零字节变化。

## 3. 新增真实性反例

- **R23**：foreign repoRoot（独立干净 git 仓库、HEAD 与 canonical 不同）→
  构造器抛 `repo_root_mismatch`；realpath 等价的拼写（尾部分隔符）仍接受；
  checker 断言精确类别。
- **R24**：注入 `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE` 指向 foreign 仓库
  → candidate 与 profile 身份不受影响（live HEAD、bound profile SHA 仍为
  canonical），完整流程照常 FINISHED；finally 恢复环境。
- **R13 语义变更（如实披露）**：原"移动 fixture HEAD 后 drift"探针随
  fixture 仓库退役——canonical 绑定下外部测试不允许移动真实 worktree HEAD。
  R13 现证明 candidate 绑定等于 canonical live HEAD 且贯穿完整流程；
  canonical HEAD 漂移的 authorize/launch 重解析路径保持 code-live（与
  R11/R12/R22 以真实字节变异所演练的同一 live 复核路径），其直接证伪需
  移动真实 HEAD，本轮禁止，已留待有授权的运行时轮。

## 4. 文件级证伪（driver 会话，快照 SHA `8c2629c1…` 字节一致恢复）

| 变异 | RED 表现 |
|---|---|
| M-A：`repo_root_mismatch` 校验恒假化 | checker rc=1，精确消息 `R23: foreign repoRoot refused at construction (category exact) did NOT throw` |
| M-B：`gitEnv()` 返回原始环境（剥离移除） | checker rc=1：注入 `GIT_DIR` 后首个 git 调用即 fail-closed 失败（foreign `.git` 无法作为有效仓库承担身份），构造被拒——注入路径不可能形成有效替换 |

- **tree integrity before == after**：6 文件 manifest SHA-256
  `0f7b349b…b5b016c` 前后相等。

## 5. 冻结门

- `git fetch --all --prune`；BASE `18d71fd1` local == remote（R3 分支远端 tip
  比对）；B1-R5-R3 候选与远端引用未修改。
- GitNexus 索引 commit == BASE `18d71fd1`；`resolveLiveHead` LOW(4)、
  `readProfileCommittedBytes` LOW(2)——无 HIGH/CRITICAL。
- `pnpm install --frozen-lockfile` PASS；`test:list` 15 tests / 1 spec 顺序
  不变；`validate:static` **14/14**（[14] 锚点扩展 `canonicalRepoRoot`/
  `repo_root_mismatch`/`gitEnv`/R23/R24）；G1–G6、runtime-contracts、
  browser-authority（R1–R24）、tsc 全绿。
- `git diff --check` clean；detect-secrets 只读 hook rc=0；4 文件 UTF-8/LF
  清洁；提交前 `detect_changes(scope=staged)`：harness 内部、0 产品流程。

## 6. 禁止项遵守

无 PG、无 Redis、无产品运行时、无非 list Playwright、无权威浏览器旅程、
无 Kilo/合并/部署；R3 候选 `18d71fd1` 及更早历史未修改、未重写、未
force-push。

## 7. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R5_R4_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW**

声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`。推送后 STOP。
下一门仅为 Kilo bounded source/test authenticity review。

**STOP。**


## ERRATUM（E1，2026-08-31）— detect_changes 数字勘误

本台账 §5 与 R4 提交信息原写"0 产品流程"沿用了前几轮的措辞，但本轮
`detect_changes(scope=staged)` 的**实测结果**为：5 files / 48 symbols /
**Affected processes: 2 / Risk level: medium**（此前轮次的 0/low 不再适用）。

两个受影响执行流均为控制面自身（harness 内部，非产品流程）：

1. `#assertLiveBindings → BrowserAuthorityError`（5 steps）
2. `#assertLiveBindings → Sha256Hex`（5 steps）

成因：B1-R5-R4 使构造器与检查点新增/改动了 `verifyChain`/`append`/
`#assertLiveBindings` 的调用形态，被索引器计入这两个 live-binding 流。
复现方式：worktree 检出 BASE `18d71fd1` → 重建索引 → 以 R4 内容暂存 5 文件
→ `detect_changes(scope=staged)`。

过程披露：R4 提交信息中的"0 processes"系提交时数字尚未捕获、沿用了旧轮
措辞所致，属发布顺序缺陷而非产品缺陷；本勘误以实测数字取代之。风险级别
medium 由索引器按 touched flows 判定，未改变本轮任何结论。
