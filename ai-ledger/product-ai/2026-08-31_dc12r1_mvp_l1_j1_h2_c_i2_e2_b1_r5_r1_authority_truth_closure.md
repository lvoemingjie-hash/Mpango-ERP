# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R5-R1 — Browser Authority Live-Binding, Terminal-State and Audit-Ledger Truth Closure

- 日期：2026-08-31（+08:00）；执行者：Zcode
- BASE：`84810870997022ab00b5a5a50c5cbb3bb75e041f`（B1-R5 候选，local == remote 已验证）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r5-r1-authority-truth-closure-2026-08-31`
- 验证层级：`V1_BOUNDED_SOURCE_AND_TEST_AUTHENTICITY`
- 声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`

## 1. Delta（相对 BASE，恰为授权的 7 个文件）

| 文件 | 类型 |
|---|---|
| `tools/browser-authority-runner.mjs` | 修改（重写） |
| `tools/check-browser-authority-contracts.mjs` | 修改（重写） |
| `tools/validate-static.mjs` | 修改（+步骤 [14]；13/13→14/14 如实披露） |
| `inventory/browser-authority-contract.schema.json` | 修改（transitions 枚举扩展 RUNNING/TEST_RED） |
| `inventory/browser-authority-profile.json` | 新增（受保护 profile，15 字段） |
| `README.md` | 修改（R1 章节） |
| 本台账 | 新增 |

package/lockfile、产品源码、既有浏览器 spec、backend/frontend、
harness-governance、迁移、`.secrets.baseline`、既有账本：零字节变化。

## 2. A — LIVE BYTE BINDING

- B1-R5 的自比较 helper 已删除（源内不可再引用；validate-static 步骤 [14]
  常驻检查）。
- **profile**：从模块相对规范路径读取 `browser-authority-profile.json` 原始
  字节，preflight/authorize/launch 三处独立重算 SHA-256；漂移即
  `profile_sha_drift` → STOPPED。
- **contract**：任务私有 contract JSON 文件为 live 字节源，authorize/launch
  重读重算（`contract_sha_drift`）。
- **input**：materialize 产物私有（`#materialized`）且**深冻结**；
  authorize/launch 重算 canonical SHA 并与 materialize 绑定及调用方期望
  双向比对（`input_sha_drift`）。
- **candidate**：`resolveLiveHead(repoRoot)` = `git -C <root> rev-parse HEAD`
  （argv 数组 subprocess）；构造、authorize、launch 各自 live 解析，绝不
  接受调用方字符串（`candidate_sha_drift`）。
- 任一漂移：STOPPED/VOID，command starts 保持真实值（未启动即 0）。

## 3. B — TERMINAL STATE TRUTH

- 七态：INIT、PREFLIGHTED、AUTHORIZED、RUNNING、FINISHED、TEST_RED、
  STOPPED；launch 先写启动哨兵再进入 RUNNING。
- 仅 `child rc==0 && reconciliation.complete` 进入 FINISHED；已启动 child
  的 rc!=0 或对账不完整 → **TEST_RED**（台账 `test_red` 记录
  child_rc_zero/reconciliation_complete 布尔），绝不 FINISHED/VOID。
- 未实际启动的执行器异常 → STOPPED，哨兵回退到真实值
  （`executor_exception` 记录 started=false 与真实 starts）。

## 4. C — ONCE-ONLY FAIL-STOP

- 第二次 preflight/authorize/launch：先落盘拒绝事件（durable JSONL），
  再进入 STOPPED，后抛精确类别（`preflight_already_invoked`/
  `authorize_already_invoked`/`launch_already_invoked`）。
- R15 证明：调用方捕获异常后再 launch → `terminal_stop`，
  **launch starts=0**（checker 显式断言），且拒绝事件已在 STOPPED 前
  持久化于 sink。

## 5. D — NON-WEAKENABLE PROFILE

- 新增受保护 `inventory/browser-authority-profile.json`：15 个 J1H2C_*
  字段（owner/W1/W2/unknown/unverified/forged-token/maildir/base/api/
  邀请码×4），逐字段 role/required/sensitive。
- **机器对账**：validate-static 步骤 [14] 与 checker S0 分别以正则抽取
  `src/env.ts` 的 `required('J1H2C_*')` 集合，与 profile env 集合做
  精确相等对账（实测 15 == 15）；preconditions/spec/scanner 的消费面即
  env.ts 契约面。
- 缺失任一实际必需字段均 fail closed：R17 逐字段删除 15/15 全 RED
  （runner `contract_field_unknown_to_profile`；owner 走
  `profile_owner_field_unknown`；checker 层 env.ts 对账标记
  profile_field_missing）。
- R18：弱化为单 owner 字段的调用方合同 → `contract_weaker_than_profile`；
  发明侧门字段 → `contract_field_unknown_to_profile`。无 CLI/env/调用方
  弱化覆盖路径。

## 6. E — DURABLE AUDIT LEDGER

- entries 私有（`#readRecords`），外部无 pop/splice/replace 面。
- 任务私有 JSONL sink；每条 `{seq, prev_sha, entry, event_sha}`
  （genesis prev = 64×'0'）。
- 每次 append：先从磁盘复读并验证 count/seq 严格序/hash 链，再写入并
  **fsync** 后返回；实例私有尾指针使**尾部截断**即使前缀链有效也 RED
  （`ledger_truncated`）。
- 尾部改写 → `ledger_chain_broken`（event_sha 重算不符，fresh reader 即可
  检出）；重复 seq → `ledger_seq_duplicate`。
- terminal evidence 必须存在 `terminal_seal`：无 seal 时 `evidence()` 抛
  `evidence_unsealed` —— 无 seal 不得形成 PASS；seal 仅限终态且唯一
  （`seal_requires_terminal_state`/`seal_already_present`）。
- 台账仍只允许名称、布尔、类别、计数（值防火墙 `sensitive_value_rejected`
  在 durable sink 上同样生效）。

## 7. 真实性反例（checker 真模块加载，全部精确类别 + 恢复 re-GREEN）

- **R1–R10**（自 B1-R5 适配 live 绑定面）：字段覆盖×2、缺 owner/W1/W2、
  错误 from + 非法边、拒绝未入账（抑制中间台账行 → seq/链守卫 RED；
  完整 sink 通过链验证）、VOID 后三面 ×(terminal_stop)、第二次 preflight
  （+STOPPED 证明）、第二次 browser（double 恰一次）、调用方 SHA 三漂移、
  argv 漂移/字符串 argv×2/空 argv、敏感值×2 + 纯类别对照。
- **R11** 授权后修改 live contract bytes → `contract_sha_drift`，STOPPED，
  **launch=0**；字节恢复后 `liveContractSha()` 与初绑一致。
- **R12** materialized input 篡改：场景级（深冻结拒绝写入、SHA 稳定、无误报
  漂移、launch 正常 FINISHED）；文件级（deepFreeze 关闭 → 篡改成功 →
  `input_sha_drift`，STOPPED，**launch=0**）。
- **R13** 授权后移动 live git HEAD（fixture 仓库 reset 到第二提交）→
  `candidate_sha_drift`，STOPPED，**launch=0**；HEAD 恢复后一致。
- **R14** child rc=1 → TEST_RED（state=TEST_RED、starts=1、可 seal 出
  TEST_RED evidence）；rc=0 但对账不完整 → TEST_RED；绝不 FINISHED/VOID。
- **R15** 第二次 preflight → 捕获 `preflight_already_invoked` → STOPPED →
  launch → `terminal_stop`，**launch starts=0**，拒绝事件已持久化。
- **R16** 台账尾部删除（同实例）→ `ledger_truncated`；尾部改写（fresh
  reader）→ `ledger_chain_broken`；重复 seq → `ledger_seq_duplicate`；
  截断 sink 上 append fail closed；恢复后 count==3 链验证通过。
- **R17** 15 个必需 profile 字段逐项删除 → 15/15 全 RED（runner 拒绝 +
  checker env.ts 对账标记），profile 逐次字节恢复。
- **R18** 单 owner 字段调用方合同 → `contract_weaker_than_profile`。
- 每项之后全新实例复跑规范 GREEN 路径（materialize→preflight→authorize→
  单次 launch→FINISHED→seal→evidence）。

## 8. 文件级证伪（driver 会话，快照 SHA-256 恢复 + tree integrity）

| 变异 | RED | 恢复 |
|---|---|---|
| F-A：`deepFreeze` 关闭 + 篡改 input 值 | `input_sha_drift`，STOPPED，starts=0 | runner 字节一致（`e60f4afa…`）→ checker GREEN |
| F-B：`resolveLiveHead` 恒定化 | R13 场景失效，checker 5 项 FAIL | runner 字节一致 → checker GREEN |
| F-C：tracked profile 删除 `api_base_url` | checker S0 对账 FAIL + static [14] "profile env set does not reconcile" | profile 字节一致 → checker + static GREEN |

- **tree integrity before == after**：7 文件范围 manifest SHA-256
  `22130c51…aaccd6` 前后相等。
- 过程披露：F-A driver 首跑因 fixture repo 目录未预创建（`git -C` 128）
  失败一次，修正 driver 后于干净态重跑；runner 当时已按快照恢复后再重跑。

## 9. 冻结门

- `git fetch --all --prune`；BASE `84810870` local == remote（B1-R5 分支
  远端 tip 比对）。
- GitNexus 1.5.3：worktree 索引 commit == BASE `8481087`（pre-edit 图）；
  编辑针对符号 upstream impact：`materializeInput` LOW(3)、`parseContract`
  LOW(1)、`ControlPlane` LOW(0)、`DurableJsonlLedger` 未入图（B1-R5 新类，
  BASE 索引中无聚合）——无 HIGH/CRITICAL，未触发 STOP。时点披露：impact
  于编辑进行中执行，但索引图构建于 BASE，结果即编辑前影响面。
- `pnpm install --frozen-lockfile`：PASS。
- `test:list`：**15 tests / 1 spec**，顺序不变。
- `validate:static` **14/14**（13/13→14/14，新增 [14]，如实披露）、
  `check:neutrality` G1–G6、`check:runtime-contracts`（含 B1-R4 loader）、
  `check:browser-authority`（R1–R18）、`tsc --noEmit`：全绿。
- `git diff --check`：clean rc=0。
- detect-secrets **只读** hook（6 个改动文件 vs `.secrets.baseline`，
  从未执行 scan --baseline 改写）：rc=0。
- 严格 UTF-8 / 无 BOM / 无 NUL / 无 CR / 无 U+FFFD / LF-only（7 文件）：
  PASS。
- 提交前 GitNexus `detect_changes(scope=staged)`：仅 harness 内部，
  无产品流程漂移（数字见提交信息）。
- delta 恰为授权 7 文件（6 M/A + 本台账）。

## 10. 禁止项遵守

无 PG、无 Redis、无产品运行时、无非 list Playwright、无权威浏览器旅程、
无 Kilo 启动、无合并或部署；B1-R5 历史（`84810870`）未修改、未重写、
未 force-push。

## 11. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R5_R1_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW**

声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`。
推送后 STOP。下一门仅为 Kilo bounded source/test authenticity review。

**STOP。**
