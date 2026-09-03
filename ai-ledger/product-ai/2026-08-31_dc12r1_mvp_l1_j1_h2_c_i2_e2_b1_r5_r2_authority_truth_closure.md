# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R5-R2 — CTO P1 Closure (Profile Override, Async Child, Tamper-Proof Evidence)

- 日期：2026-08-31（+08:00）；执行者：Zcode
- BASE：`bd823e06da41fbe147e219ba91dbe7e96d8310af`（B1-R5-R1 候选；候选与远端
  引用未修改）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r5-r2-authority-truth-closure-2026-08-31`
- 验证层级：`V1_BOUNDED_SOURCE_AND_TEST_AUTHENTICITY`
- 声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`
- 输入：CTO 裁决 `NEED_CHANGES_BEFORE_KILO_REVIEW`（三项 P1 独立反例：
  weakProfileAndContractAccepted=true；async child immediateOutcome=TEST_RED
  且终态 TEST_RED；tampered ledger evidence accepted=true）

## 1. Delta（恰为授权范围：4 文件 + 本台账 = 5 路径）

| 文件 | 类型 |
|---|---|
| `tools/browser-authority-runner.mjs` | 修改（三项 P1 修复） |
| `tools/check-browser-authority-contracts.mjs` | 修改（greenPath 适配 + R19/R20/R21） |
| `tools/validate-static.mjs` | 修改（步骤 [14] 锚点扩展 R19-R21/async/chain-forced） |
| `README.md` | 修改（R2 小节） |
| 本台账 | 新增 |

package/lockfile、产品源码、spec、backend/frontend、harness-governance、
profile、schema、.secrets.baseline、既有账本：零字节变化。

## 2. P1-1 — profile 覆盖入口删除

生产构造器签名收窄为 `{ contractPath, repoRoot, ledger }`：
`profilePath` 参数不复存在，受保护 profile **永远**绑定模块相对规范路径
`inventory/browser-authority-profile.json`（私有字段仅缓存 canonical 绑定）。
调用方传入的 `profilePath` 属性被解构丢弃，不存在任何生效路径。

- 新增 **R19**：弱 profile + 弱合同 + 显式 `profilePath` 覆盖尝试 → 覆盖被
  忽略，canonical profile 拒绝弱合同（`contract_weaker_than_profile`）；
  完整合同 + 伪造 profilePath → 绑定 SHA 仍为 canonical profile
  （`boundProfileSha()` 比对）。

## 3. P1-2 — launch 等待真实子进程结局

`launch()` 保持同步守卫（守卫失败仍同步抛出），但分类不再立即进行：
实现返回 **Promise** 时，控制面 `Promise.resolve(...).then(...)` 等待真实
进程结束再分类：

- settle 为 `{rc:0, reconciliation.complete:true}` → RUNNING→**FINISHED**；
- settle 为 rc!=0 或对账不完整，或 **Promise reject**（异步 child 失败，
  已真实启动）→ RUNNING→**TEST_RED**（台账 `test_red`，`async_failure`
  布尔），绝不 FINISHED/VOID；
- 实现同步抛出（未实际启动）→ 哨兵回退真实值，STOPPED（`executor_exception`
  started=false，starts=0）——与 B1-R5-R1 语义一致。

新增 **R20**：(a) Promise 成功 → **FINISHED**（state/starts 终值断言）；
(b) Promise reject → `test_red_async_child_failure`，TEST_RED，starts=1；
(c) 同步 executor 异常 → STOPPED，starts=0。

## 4. P1-3 — 篡改台账不得出具证据

`seal()` 与 `evidence()` 现在都**先执行完整 on-disk `verifyChain()`**（count
+ 严格 seq + prev_sha/event_sha 链重算 + 私有尾指针截断检查），随后才检查
terminal seal。早期记录被篡改（即便保留 seal 及其后全部行）→ 链重算不符 →
`ledger_chain_broken`，`evidence()` 拒绝出具，`seal()` 拒绝再封。

新增 **R21**：完整 GREEN→seal→evidence 读取 OK；篡改 `finish` 记录
（保留 seal 行与旧 event_sha）→ `evidence()` 抛 `ledger_chain_broken`、
`seal()` 同样先撞链复核；恢复原始字节后 evidence 重新可读。

## 5. 真实性反例与文件级变异

- checker 现覆盖 **S0 + G + R1–R21**（真模块加载、fixture git 仓库、
  durable JSONL sink），每例精确类别 + 全新实例恢复 re-GREEN。
- 文件级变异（driver 会话，快照 SHA `7b41c9b7…` 字节一致恢复，
  checker 恢复后 rc=0）：

| 变异 | RED 表现 |
|---|---|
| M-A：构造器重新接受 `profilePath`（canonical 绑定后覆盖） | checker rc=1：R19 第二构造器抛未捕获 `contract_field_unknown_to_profile`（弱 profile 拒绝完整合同），R19 断言不通过 |
| M-B：launch 恢复"立即分类 Promise 对象"缺陷 | checker rc=1：R20 "async successful child -> FINISHED" 失败（Promise 对象被误判） |
| M-C：`evidence()` 移除链复核 | checker rc=1：R21 "tampered early record refused … did NOT throw" |

- **tree integrity before == after**：6 文件范围 manifest SHA-256
  `13d27894…8bc2ce0` 前后相等。

## 6. 冻结门

- `git fetch --all --prune`；BASE `bd823e06` local == remote（R1 分支远端
  tip 比对）；B1-R5-R1 候选与远端引用未修改。
- GitNexus 索引 commit == BASE `bd823e0`；编辑符号 impact：`launch` LOW(1)、
  `evidence` LOW(1)、`seal` LOW(0)——无 HIGH/CRITICAL。
- `pnpm install --frozen-lockfile`：PASS；`test:list`：15 tests / 1 spec
  顺序不变；`validate:static` **14/14**（[14] 锚点扩展 R19-R21/async/
  chain-forced）；`check:neutrality`、`check:runtime-contracts`、
  `check:browser-authority`（R1–R21）、`tsc --noEmit`：全绿。
- `git diff --check` clean；detect-secrets 只读 hook rc=0；7 文件
  UTF-8/LF 清洁（实测 4+台账）。
- 提交前 GitNexus `detect_changes(scope=staged)`：harness 内部，
  0 产品流程漂移。

## 7. 禁止项遵守

无 PG、无 Redis、无产品运行时、无非 list Playwright、无权威浏览器旅程、
无 Kilo/合并/部署；R1 候选 `bd823e06` 未修改。

## 8. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R5_R2_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW**

三项 P1 全部关闭并带反例回归锁定；声明上限
`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`。推送后 STOP。下一门仅为
Kilo bounded source/test authenticity review。

**STOP。**
