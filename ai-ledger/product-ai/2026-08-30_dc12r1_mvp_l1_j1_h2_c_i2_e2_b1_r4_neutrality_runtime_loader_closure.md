# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R4 — Neutrality Type-Only Import and Runtime Loader Closure

- 日期：2026-08-30（+08:00）；执行者：Zcode
- BASE：`86f41b93a3aa0e3c55724b75fc2e2aa4c6dee35b`（E1 immutable candidate）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r4-neutrality-runtime-loader-closure-2026-08-30`
- 验证层级：`V3_MERGE_CRITICAL_HARNESS_FIX`
- 声明上限：`HARNESS_FIX_CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`

## 1. 引用证据（本地 == 远端，fetch --all --prune 后逐一验证）

| 角色 | SHA | 远端 |
|---|---|---|
| BASE | `86f41b93…` | `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-current-baseline-reintegration-2026-08-30` |
| KILO_FINAL | `1b84cfe0…` | `origin/kilo/review/dc12r1-mvp-l1-j1-h2-c-i2-e2-v1-final-cumulative` |
| E2_REPORT | `df40a202…` | `origin/reports/dc12r1-mvp-l1-j1-h2-c-i2-e1-immutable-candidate-publication-2026-08-30` |
| LUBUNTU_V2 | `ef33a882…` | `origin/reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-v2-lubuntu-independent-backend-browser-final-2026-08-30` |
| PROTECTED_BASELINE | `24a28d76…` | CT2-M1 tip（候选祖先） |

## 2. 根因（Phase 1 证明）

1. `src/neutrality-core.ts:64` — `CanonicalFingerprint` 仅为
   `export interface`（类型-only，无值导出）；文件唯一运行时依赖是
   `node:crypto`。
2. BASE 的 `src/neutrality.ts:12` 将其置于**值导入**块
   （`import { CanonicalFingerprint, … } from './neutrality-core.js'`）。
   在真实 Node ESM / Playwright 运行时加载下，值导入的绑定要求模块提供同名
   运行时导出 → 加载期
   `SyntaxError: The requested module './neutrality-core.js' does not provide
   an export named 'CanonicalFingerprint'`。`tsc --noEmit` 为 GREEN 是因为
   无 `verbatimModuleSyntax` 时转译期会消除仅用于类型位置的导入——这正是缺陷
   在静态类型门下不可见、却在浏览器加载期爆发的真实根因。与 Lubuntu V2
   `ef33a882` 报告的 `BROWSER_NOT_RUN_BLOCKED_BY_HARNESS_RUNTIME_DEFECT`
   一致。

## 3. 影响分析（Phase 1.5）

GitNexus 1.5.3 在 BASE（indexed commit `86f41b9` == current）上执行：

- `fingerprintNeutralResponse` upstream：impactedCount=0，**risk LOW**；
- `assertFourStateCanonicalEquality` upstream：impactedCount=0，**risk LOW**。

无 HIGH/CRITICAL，未触发 STOP。文本层消费者如实披露：两者仅被
`tests/recovery.spec.ts` 导入使用；`validate-static.mjs` 步骤 [9] 对
`assertFourStateCanonicalEquality` 有锚点检查（本轮后仍 GREEN）。

## 4. 最小修复（Phase 2）

`src/neutrality.ts`：`CanonicalFingerprint` 改为显式
`import type { CanonicalFingerprint } from './neutrality-core.js';`；
`NeutralEnvelopeError`、`assertFingerprintsEqual`、`canonicalFingerprint`
保持运行时值导入。canonical neutrality 语义、错误分类、原始 body 生命周期
零变化（未触碰任何函数体）。

## 5. 机器强制回归门（Phase 3）

1. `tools/validate-static.mjs` 新增步骤 **[12]**（TypeScript AST 结构检查，
   非子串匹配）：`CanonicalFingerprint` 只能经 `import type`（clause 级或
   element 级 `isTypeOnly`）从 `./neutrality-core.js` 进入 src 模块；任何
   同名值导入（非 type-only 命名绑定）即 FAIL。计数 11/11 → **12/12**
   （计数变化如实披露）。
2. `tools/check-runtime-contracts.mjs` 新增 **B1-R4 loader** 段：将真实的
   `neutrality-core.ts`、`assertions.ts`、`neutrality.ts` 三模块（零实现
   复制）以 `verbatimModuleSyntax=true` 转译为独立 ESM（该配置保留错误的值
   导入、仅消除显式 `import type`），真实 Node loader 动态 import。
3. Loader smoke：`neutrality.js` 真实加载；导出既有运行时 API
   （`fingerprintNeutralResponse`、`assertFourStateCanonicalEquality`、
   `NeutralEnvelopeError`）；`CanonicalFingerprint` 不是运行时绑定；加载后
   的 core 语义冒烟（timestamp-only 差异 canonical 相等；message/extra-key/
   success/data 漂移按精确 `NeutralEnvelopeError.category` 拒绝）全部成立。
4. 临时转译目录 `mkdtempSync` + `finally { rmSync(recursive, force) }`；
   无 tracked artifact。

## 6. 变异证伪（Phase 4）

对最终候选 `src/neutrality.ts`（快照 SHA-256
`4e56641b510bb581fc615a60d9da30f97d9e32dfa215989670ec9b8a0e1d4f10`）：

| 步骤 | 结果 |
|---|---|
| 变异回值导入 | applied（单锚点替换） |
| `validate:static` | **RED rc=1**：`[12] FAIL — CanonicalFingerprint value import in neutrality.ts (type-only interface)`（+ no type-only import found），精确 step-12 消息，非锚点错误 |
| 独立 loader smoke（独立 node 进程，verbatimModuleSyntax 转译 + 动态 import） | **RED**：真实 `SyntaxError: The requested module './neutrality-core.js' does not provide an export named 'CanonicalFingerprint'`——精确缺失导出错误模式，非 PATCH ANCHOR ERROR/未命中/其他错误 |
| `check:runtime-contracts` | **RED rc=1**：`B1-R4: neutrality.js failed to load under verbatimModuleSyntax (…does not provide an export named 'CanonicalFingerprint')` |
| 字节恢复 | neutrality.ts SHA-256 == 快照 **byte-identical** |
| 恢复后全门 | validate:static 12/12 GREEN、contracts（含 B1-R4 loader）GREEN、G1–G6 GREEN、tsc GREEN、list 15/1 GREEN |

## 7. 冻结门（Phase 5，全部在本轮 worktree 执行）

- `pnpm install --frozen-lockfile`：PASS。
- `pnpm run test:list`：**15 tests / 1 spec**，顺序不变（validate-static
  步骤 [3] ordered-equal 同步验证）。
- `pnpm run validate:static`：**12/12 PASS**（步骤计数 11→12，新增 [12]，
  如实披露）。
- `pnpm run check:neutrality`（G1–G6）：PASS。
- `pnpm run check:runtime-contracts`（含新 B1-R4 loader 段）：PASS。
- `pnpm run typecheck`：PASS。
- `git diff --check`：clean。
- scoped pre-commit + read-only detect-secrets（对本轮 3 个 harness 文件 +
  台账）：PASS / 0 findings。
- 严格 UTF-8 / 无 BOM / 无 NUL / LF-only（改动文件）：PASS。
- 未启动产品运行时、PG、Redis、Playwright 浏览器旅程或后端 full-suite。

## 8. 证据真相（Phase 6）

- **BACKEND_V2_RESULT=INDEPENDENT_ZERO_RED_AT_BASE_86f41b93**
  （Lubuntu V2 `ef33a882`：全后端 3784 = 3721 passed + 48 skipped +
  15 xfailed，failed=0/errors=0/gap=0，AUTHORITY_EXECUTED_GREEN，
  绑定 candidate `86f41b93`。该结果归属 Lubuntu V2 轮，**不是**本候选的
  执行结果。）
- **BACKEND_REUSE_STATUS=ELIGIBLE_PENDING_BYTE_IDENTITY_AND_NEW_SHA_PREFLIGHT**
  （后端证据复用资格待：本候选相对 BASE 仅 3 个 harness 文件 + 1 台账、
  产品字节零变化的字节同一性证明，以及独立新 SHA preflight。）
- **BROWSER_STATUS=NOT_RUN_IN_THIS_FIX_ROUND**
  （本轮未执行任何浏览器旅程；权威浏览器运行仍是后续独立授权门。）

不把 `ef33a882` 的后端 PASS 伪装为本候选执行结果。

## 9. Delta 与收尾（Phase 7）

- 相对 BASE delta 恰为授权的 3 个 harness 文件 + 1 个新台账（本文件）：
  `j1h2c-retailer-recovery/src/neutrality.ts`、
  `j1h2c-retailer-recovery/tools/check-runtime-contracts.mjs`、
  `j1h2c-retailer-recovery/tools/validate-static.mjs`、
  `ai-ledger/product-ai/2026-08-30_…b1_r4_neutrality_runtime_loader_closure.md`。
- product/backend/frontend、tests、harness-governance、package.json、
  pnpm-lock.yaml、inventory、Playwright spec、配置、冻结报告、历史
  evidence：零字节变化。
- GitNexus `detect_changes`：仅 harness 内部，无产品流程漂移。
- 普通提交 + 普通 push（无 amend/rebase/force-push）；local == remote；
  冻结 refs 不变；worktree clean。

## 10. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW**

声明上限：`HARNESS_FIX_CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`。
下一门仅为 Kilo bounded delta review；不自行启动 Lubuntu、合并或部署。

**STOP。**
