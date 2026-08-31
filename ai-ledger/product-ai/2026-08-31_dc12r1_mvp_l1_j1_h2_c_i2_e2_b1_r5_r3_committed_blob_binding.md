# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R5-R3 — Committed-Blob Profile Binding (Dirty-Tree Closure)

- 日期：2026-08-31（+08:00）；执行者：Zcode
- BASE：`0e711e32200ab4741c11cb51752d9adbfea4c455`（B1-R5-R2 候选；候选与远端
  引用未修改）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r5-r3-authority-committed-binding-2026-08-31`
- 验证层级：`V1_BOUNDED_SOURCE_AND_TEST_AUTHENTICITY`
- 声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`
- 输入：CTO 裁决 `NEED_CHANGES_BEFORE_KILO_REVIEW`（P1 候选字节绑定缺陷：
  构造器读取工作树 profile 作为初始真值，仅检查 `git rev-parse HEAD`，未证明
  profile 字节等于该 HEAD 的 committed blob；独立反例 HEAD 不变时同时弱化
  canonical profile 与合同，控制面成功构造，`category=null`）

## 1. 修复

`tools/browser-authority-runner.mjs` 新增 `readProfileCommittedBytes(path)`：
经 `git -C <profile目录> rev-parse --show-toplevel` 定位 profile 所属仓库，
以 `git cat-file blob HEAD:<repo相对路径>`（argv 数组 subprocess）读取
**committed 字节**。绑定语义升级为：

- **构造时**：working-tree profile SHA-256 必须等于 committed blob SHA-256，
  否则拒绝构造（`profile_dirty_vs_head`）——脏树（含未跟踪改动）不可作为
  绑定源；
- **preflight/authorize/launch 每个检查点**：重复上述证明，脏 profile 一经
  检出即 STOPPED/VOID（`profile_dirty_vs_head`）；
- 未在 HEAD 中跟踪（cat-file 失败）同样 fail closed。

与既有 live 绑定叠加：candidate（live `rev-parse HEAD`）、contract（任务
私有文件 live 字节）、input（私有深冻结重算）、argv SHA、profile committed
证明——五重绑定。

## 2. Delta（恰为 4 文件 + 本台账）

`tools/browser-authority-runner.mjs`（修改）、
`tools/check-browser-authority-contracts.mjs`（修改，+R22）、
`tools/validate-static.mjs`（修改，[14] 锚点扩展）、`README.md`（修改，R3
小节）、本台账。产品/spec/harness-governance/package/lockfile/profile/
schema/.secrets.baseline/既有账本：零字节变化。

## 3. R22 — CTO 反例回归锁定

复现 CTO 反例形态：HEAD 不变，将 canonical profile 整体弱化为单 owner 字段
写入工作树，并配弱合同 → 构造器抛 `profile_dirty_vs_head`（弱合同与完整
合同两种配对均拒绝）；finally 恢复原始字节（SHA-256 相等验证）；前置条件
由 checker 自身以 `git cat-file` 证明工作树确实脏。恢复后全新实例规范
GREEN 路径通过。

## 4. 文件级证伪

F-R22：将构造器的 committed-blob 比较恒假化（`if (false && …)`）→ checker
RED rc=1，精确消息 `R22: dirty profile + weak contract refused (HEAD
unchanged) did NOT throw`；runner 按快照 SHA `a705cf91…` 字节一致恢复 →
checker GREEN rc=0。**tree integrity before == after**：6 文件 manifest
SHA-256 `ed47c1cd…f307c62` 前后相等。

## 5. 冻结门

- `git fetch --all --prune`；BASE `0e711e32` local == remote（R2 分支远端
  tip 比对）；B1-R5-R2 候选与远端引用未修改。
- GitNexus 索引 commit == BASE `0e711e3`；`resolveLiveHead` LOW(4)、
  `canonicalProfilePath` LOW(1)——无 HIGH/CRITICAL。
- `pnpm install --frozen-lockfile` PASS；`test:list` 15 tests / 1 spec 顺序
  不变；`validate:static` **14/14**（[14] 锚点扩展
  `readProfileCommittedBytes`/`profile_dirty_vs_head`/R22）；G1–G6、
  runtime-contracts、browser-authority（R1–R22）、tsc 全绿。
- `git diff --check` clean；detect-secrets 只读 hook rc=0；4 文件 UTF-8/LF
  清洁；提交前 `detect_changes(scope=staged)`：harness 内部、0 产品流程。

## 6. 禁止项遵守

无 PG、无 Redis、无产品运行时、无非 list Playwright、无权威浏览器旅程、
无 Kilo/合并/部署；B1-R5-R2 及更早历史未修改、未重写、未 force-push。

## 7. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R5_R3_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW**

声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`。推送后 STOP。
下一门仅为 Kilo bounded source/test authenticity review。

**STOP。**
