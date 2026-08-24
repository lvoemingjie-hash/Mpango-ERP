# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R2-V1 — Kilo Final Cumulative Harness Authenticity Review

- 日期：2026-08-24（+08:00）；审查者：Kilo
- 模式：独立、有界、对抗性源码与真实性审查（冻结 Playwright harness，双主机 EOL 可移植性）
- 目标裁决：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R2_V1_KILO_FINAL_HARNESS_REVIEW`

## 冻结输入

| 项目 | 值 |
|------|-----|
| Harness candidate | `cb35207969fc1b0c8d8488ac65d75e47fedc3f23` |
| Harness branch | `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r2-app-settle-eol-portability-2026-08-24` |
| B1-R2 parent | `e65e9a7f61c78906c2c5874d6589d4bada23942c` |
| Product candidate | `8c462170804322d3f73803d8991c00879582e232` |
| Protocol | `132cf7edaac5d6c57ebcdc2465334f4aa465aab2` |
| Backend Kilo | `4d42ffcae09d3a362f778c1e0661a72e1147dcba` |
| Lubuntu zero-red | `5570093ec7f9e3dc2b4083ac8c091aae75a62d1d` |
| Protected baseline | `6e9470a1daa5d6eece29724316fdd8aef6b737c1` |

## Phase 1 — Proof And Scope

| 步骤 | 结果 |
|------|------|
| `git fetch --all --prune` | 通过 |
| harness candidate == remote branch tip | 通过（`cb352079` == `origin/zcode/...`） |
| `candidate^` == `e65e9a7f` | 通过 |
| `e65e9a7f^` == `8c462170` | 通过 |
| `origin/product-dev-recovered` == `6e9470a1` 且未漂移 | 通过 |
| detached isolated worktree clean | 通过 |
| B1-R2 delta 恰好 5 个授权文件 | 通过 |
| 相对产品候选 8c462170，产品路径字节不变 | 通过 |
| Harness 当前恰好 22 个文件 | 通过 |

### B1-R2 Delta 文件清单（5 文件）
1. `j1h2b-forgot-reset/.gitattributes` — EOL 可移植性规则
2. `j1h2b-forgot-reset/tests/forgot-reset.spec.ts` — R12 application-settle 条件替换 networkidle
3. `j1h2b-forgot-reset/tools/validate-static.mjs` — 新增 networkidle 禁止标记、R12 app-settle 校验、EOL 可移植性校验
4. `j1h2b-forgot-reset/README.md` — 记录 B1-R2 变更
5. `j1h2b-forgot-reset/FROZEN-REPORT.md` — 记录 B1-R2 冻结报告

### Harness 文件清单（22 文件）
```
j1h2b-forgot-reset/.gitattributes
j1h2b-forgot-reset/.gitignore
j1h2b-forgot-reset/FROZEN-REPORT.md
j1h2b-forgot-reset/README.md
j1h2b-forgot-reset/inventory/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_node_inventory.csv
j1h2b-forgot-reset/inventory/node-registry.json
j1h2b-forgot-reset/package.json
j1h2b-forgot-reset/playwright.config.ts
j1h2b-forgot-reset/pnpm-lock.yaml
j1h2b-forgot-reset/src/api-client.ts
j1h2b-forgot-reset/src/assertions.ts
j1h2b-forgot-reset/src/env.ts
j1h2b-forgot-reset/src/leak-scan.ts
j1h2b-forgot-reset/src/maildir.ts
j1h2b-forgot-reset/src/neutrality.ts
j1h2b-forgot-reset/src/reconciliation.ts
j1h2b-forgot-reset/src/token-store.ts
j1h2b-forgot-reset/src/ui-journey.ts
j1h2b-forgot-reset/tests/forgot-reset.spec.ts
j1h2b-forgot-reset/tools/scan-artifacts.mjs
j1h2b-forgot-reset/tools/validate-static.mjs
j1h2b-forgot-reset/tsconfig.json
```

## Phase 2 — Inventory And Fail-Stop

| 要求 | 结果 | 证据 |
|------|------|------|
| protocol CSV committed blob 与 `132cf7ed` 字节一致 | 通过 | `git hash-object` 计算 CSV blob = `29a2bdd30b8ffd9142404dd530486d7fa6fd1f15`，与协议一致 |
| CSV 严格为 29 行 × 15 列 | 通过 | 首行 15 列 header，合计 30 行（header + 29 rows） |
| browser 24、non-browser 5 | 通过 | browser: F1-D/T/M, F2-D/T/M, F3, F4, F5, R1, R2, R3, R4, R5, R7-POLICY, R7-POLICY-M, R8, R8-M, R9, R10, R10-M, R11, R12, M1；non-browser: F6, R6, M2, R13, RT0 |
| `--list` 精确 24，标题和顺序与 browser inventory 完全一致 | 通过 | `pnpm exec playwright test --list` 输出 24 tests in 1 file，标题集合与顺序与 CSV browser 行完全一致 |
| 唯一 spec 为 `tests/forgot-reset.spec.ts` | 通过 | `tests/` 目录下仅一个 `.spec.ts` 文件 |
| 单一外层 serial describe 真实包裹全部 24 节点 | 通过 | `test.describe.configure({ mode: 'serial' })` + 24 个 `test()` 节点 |
| `fullyParallel:false`、`workers:1`、`retries:0`、`maxFailures:1` | 通过 | `playwright.config.ts` 显式声明 |
| F6/R6/M2/R13/RT0 不得出现在 browser PASS 中 | 通过 | 五个 non-browser 节点均未出现在 `tests/forgot-reset.spec.ts` 中 |
| RT0 保持 `BLOCKED_BY_H2_C`，无 API 绕过 | 通过 | `node-registry.json` 中 RT0 status = `BLOCKED_BY_H2_C`；源码中无 retailer forgot-reset API 调用 |

## Phase 3 — State And Timing Authenticity

| 要求 | 结果 | 证据 |
|------|------|------|
| token/state 只在单一 serial spec 的同一 worker 内存中传递 | 通过 | `src/token-store.ts` 模块级 `const state` 仅由 `tests/forgot-reset.spec.ts` 读写；`workers=1` + `mode:'serial'` 保证单进程单线程顺序执行 |
| 不依赖文件名排序或跨 spec 模块缓存 | 通过 | 仅一个 spec 文件；状态传递通过显式函数调用（`a1State()`, `m1State()`），非文件名或全局缓存 |
| 首个失败后不会继续制造级联红节点 | 通过 | `maxFailures: 1` + 单一 serial spec 保证首败即 STOP |
| R2 等待真实 URL/hash 清洗条件 | 通过 | `page.waitForFunction(() => window.location.hash === '' && window.location.pathname === '/reset-password', { timeout: 15_000 })` |
| R12 有界等待同时证明 pathname、hash、#newPassword 可见且可交互 | 通过 | `page.waitForFunction(() => window.location.pathname === '/reset-password' && window.location.hash === '', { timeout: 15_000 })` + `await expect(page.locator('#newPassword')).toBeEditable()`；条件满足后立即执行 leak scan |
| R12 不含 networkidle、waitForTimeout 或固定 sleep | 通过 | `validate-static.mjs` 禁止标记扫描确认无 `networkidle`、无 `waitForTimeout`；源码审查确认无 `sleep` |
| 无 waitForTimeout、sleep、重试或条件通过 | 通过 | `validate-static.mjs` 扫描确认无 `waitForTimeout`；源码审查确认无 `sleep`、无 `retry`、无 `test.skip`/`test.only`/`describe.only`/`describe.skip` |

## Phase 4 — Journey Authenticity

逐节点源码核验（不执行浏览器旅程）：

| 节点 | UI 真实性 | 证据 |
|------|-----------|------|
| F1/F2 | 真实登录页入口和表单 | `page.goto('/login')` → `expectForgotEntryVisible` → `clickForgotEntry` → `expectForgotFormStructure` |
| F3/F4/F5 | 经 UI 提交，中性比较只保留 status/hash/length | `submitForgot(page, email)` → `expectNeutralForgotCopyVisible` → `captureForgotFingerprint`；`sameFingerprint` / `firstFingerprintDifference` 比较 |
| R1/R2 | fragment-only 与 URL 清洗真实执行 | `openResetLink(page, hit.link)` → `expectResetFormRendered` → `waitForFunction` 验证 hash 剥离 |
| R3 | query token 拒绝且 reset API 调用数为 0 | `page.goto('/reset-password?resetToken=...')` → `expectInvalidLinkPanelVisible`；`urlsMatching(apiRequests, /reset-password/).length === 0` |
| R4/R5 | 缺失与伪造 token fail closed | R4: 无 token 提交 → `expectResetServerErrorVisible`，零 API 调用；R5: 伪造 token → `waitForResponse` 断言 401 |
| R7 | 两视口弱密码 UI 拦截且零 API | `page.locator('#newPassword').fill('x'.repeat(7))` → `expect(page.getByText('Password must be at least 8 characters')).toBeVisible()`；`urlsMatching(...).length === 0` |
| R8/R8-M | 完整 UI reset，不复用虚假成功状态 | 每轮独立 `openResetLink` + `submitReset` + `waitForResponse` 断言 200 + `expectResetSuccessVisible` |
| R9/R10/R11 | 真实登录验证旧密码拒绝、新密码接受、重放拒绝且 P2 仍有效 | R9: `loginViaUi` with P1 → 401；R10: `loginViaUi` with P2 → `waitForURL('/')`；R11: 同一 link 重放 → 401，随后 P2 仍可登录 |
| R12 | 扫描 URL/storage/console/network metadata | `scanUrl` + `scanStorage` + `scanConsoleText` + `scanNetworkRequest` + `scanSecretSubstrings`；失败输出仅含 `describeFindings(findings)`，不含秘密值 |
| M1 | 两个独立 browser context 验证双租户 P1/P2 | `browser.newContext()` 创建 contextA/contextB；各执行 `proveOldPasswordRejectedNewAccepted`，验证双侧 admin role + 双工作区 |

禁止将 helper 返回值、直接 API 响应或硬编码布尔值当作 UI 成功证明。——源码审查确认所有成功断言均基于 Playwright `expect` / `waitForResponse` / `waitForURL` 等真实浏览器条件。

## Phase 5 — Provisioning Boundary

| 要求 | 结果 | 证据 |
|------|------|------|
| M1 前置严格使用正式 API | 通过 | `src/api-client.ts` 中 `signupWholesaler` → `verifySignupEmail` → `consumeOwnerSetup` → `loginIdentity` → `selectTenant` → `PUT /users/{id}/roles` |
| W1/W2 owner 不同邮箱 | 通过 | `env.m1.w1.ownerEmail` ≠ `env.m1.w2.ownerEmail`（`env.ts` distinctness 校验） |
| M 为同一规范化邮箱 | 通过 | `env.m1.m.email` 经 `requireEmail` 归一化 |
| 两次用户创建使用同一 P1 | 通过 | `env.m1.m.initialPassword` 用于两侧创建 |
| 双侧正式 admin role | 通过 | `PUT /users/{id}/roles` with `ADMIN_ROLE` + `ADMIN_PERMISSIONS` |
| 登录必须精确返回 W1/W2 | 通过 | `expectWorkspaceSelectorWithBoth(page, w1Name, w2Name)` |
| API 仅用于供给前置和协议允许的只读后置条件 | 通过 | `api-client.ts` 注释明确 "Nothing else. Forgot/reset journey actions are performed exclusively through the rendered UI" |
| forgot/reset 动作无 fetch/API helper 绕过 | 通过 | 所有 forgot/reset 步骤通过 `submitForgot` / `openResetLink` / `submitReset` / `loginViaUi` 等 UI helper 执行 |
| 无 SQL、ORM、手写 hash、debug endpoint 或数据库修补 | 通过 | 源码审查确认无此类模式 |

## Phase 6 — Secret And Evidence Boundary

| 要求 | 结果 | 证据 |
|------|------|------|
| 成功认证凭据全部来自环境变量，缺失 fail closed | 通过 | `loadJourneyEnv` 调用 `requireEnvVar` / `requireAll`，缺失时抛错命名变量名，不回显值 |
| maildir token 只存在于内存 | 通过 | `src/maildir.ts` 读取链接后返回内存对象；`token-store.ts` 注释明确 "never written to disk, never logged" |
| trace/screenshot/video 关闭 | 通过 | `playwright.config.ts` 设置 `trace: 'off'`, `screenshot: 'off'`, `video: 'off'` |
| JSON/JUnit/list/错误消息不输出 token、密码、Authorization、URL fragment 或响应原文 | 通过 | `assertSan` 错误消息仅含字段名（如 `field: status`）；`leak-scan.ts` 扫描五面证据 |
| assertSan 和 leak scanner 不会在失败时插入被检测的实际值 | 通过 | `assertSan` 模板字符串仅插值字段名；`scanSecretSubstrings` 仅报告 `surface + field` |
| artifact scanner 覆盖 R13 的全部预期产物 | 通过 | `tools/scan-artifacts.mjs` 扫描 machine JSON、JUnit、CSV backfill、日志、截图 |

## Phase 7 — Independent Mutation Gates

| 突变 | 预期 | 实际 | 结果 |
|------|------|------|------|
| M1: 恢复 networkidle | RED | `forbidden marker networkidle found in tests\forgot-reset.spec.ts` | 通过 |
| M2: 删除 pathname/hash 条件 | RED | `R12 must wait for the application-settle pathname condition` + `R12 must wait for the empty-hash condition` | 通过 |
| M3: 删除 #newPassword 可交互条件 | RED | `R12 must wait for the reset form #newPassword to be visible and interactable` | 通过 |
| M4: 删除 .gitattributes | RED | `j1h2b-forgot-reset/.gitattributes must exist (EOL portability contract)` + `.gitattributes must contain the rule '* text=auto eol=lf'` | 通过 |
| M5: eol=lf 改成 eol=crlf | RED | `.gitattributes must not contain any eol=crlf rule` | 通过 |
| 恢复后 candidate tracked bytes 与原 SHA 一致 | GREEN | `git status` clean，`HEAD` = `cb352079` | 通过 |
| 恢复后所有静态门重新 GREEN | GREEN | `validate-static.mjs` 6/6 steps PASSED | 通过 |

## Phase 8 — Dual-Host Reviewer Runtime

### Kilo Windows Host (`core.autocrlf=true`)

| 检查 | 结果 | 备注 |
|------|------|------|
| `pnpm install --frozen-lockfile` | PASSED | exact pins: @playwright/test 1.49.1 / @types/node 22.10.5 / typescript 5.7.3 |
| Playwright `--list` | PASSED | 24 tests in 1 file，标题集合与顺序与 inventory browser 行完全一致 |
| `validate-static.mjs` | PASSED | 6/6 steps PASSED — `.gitattributes` 强制 LF，CRLF 主机限制已关闭 |
| `tsc --noEmit` | PASSED | zero diagnostics |
| mutation gates M1-M5 | PASSED | 全部产生预期 RED，恢复后 GREEN |
| `git diff --check` | PASSED | 无 whitespace/merge conflict artifacts |
| `detect-secrets` | PASSED | harness scan clean |
| UTF-8/no-BOM/no-CR | PASSED | 22 个 harness 文件全部通过 |
| GitNexus `analyze`/`status` | PASSED | 28,732 nodes / 59,981 edges / up-to-date |

### Lubuntu Linux Host（原生 Linux fresh checkout）

| 检查 | 结果 | 备注 |
|------|------|------|
| `pnpm install --frozen-lockfile` | PASSED | 同 exact pins |
| Playwright `--list` | PASSED | 24 tests in 1 file，顺序一致 |
| `validate-static.mjs` | PASSED | 6/6 steps PASSED |
| `tsc --noEmit` | PASSED | zero diagnostics |
| `git diff --check` | PASSED | 无 whitespace artifacts |
| `detect-secrets` | PASSED | harness scan clean |
| UTF-8/no-BOM/no-CR | PASSED | 22 个 harness 文件全部通过 |

### EOL 可移植性结论
- `.gitattributes` 规则 `* text=auto eol=lf` 在 Windows `core.autocrlf=true` 和 Linux 原生环境下均强制 LF checkout。
- `validate-static.mjs` 步骤 6 的 CR 字节检查在两端均通过。
- B1-R2 已关闭 B1-R1 的 Windows CRLF `HOST_LIMITATION`。

## 历史裁决

| 历史裁决 | 当前状态 |
|----------|----------|
| Kilo B1-R1 PASS | **SUPERSEDED_BY_B1_R2_SETTLE_AND_EOL_PORTABILITY_CLOSURE** |
| Lubuntu B1-R1 networkidle STOP | **CLOSED_BY_B1_R2** — networkidle 已从 R12 移除，替换为 application-settle 条件（pathname + hash + #newPassword editable） |

## 裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R2_V1_KILO_FINAL_HARNESS_REVIEW
```

- Harness candidate `cb352079` 通过全部 Phase 1–7 对抗性审查。
- B1-R2 delta 精确限定为 5 个授权文件，产品/测试/migration/模型/依赖/前端/部署零变化。
- Harness 恰好 22 个文件，Inventory 29×15、24 browser + 5 non-browser、协议 CSV blob 字节一致。
- R12 已移除 `networkidle`，替换为 application-settle 条件（pathname + hash + #newPassword editable），条件满足后立即执行 leak scan。
- `.gitattributes` 强制 LF checkout，关闭双主机 EOL 可移植性问题。
- 单一 serial spec + `maxFailures:1` + `workers=1` + `retries=0` 满足 fail-stop 要求。
- 状态仅在单 spec 单 worker 内存中传递，无跨 spec 缓存或文件名排序依赖。
- 所有 5 项 mutation 均产生预期 RED，恢复后候选字节一致。
- 双主机（Kilo Windows + Lubuntu Linux）静态检查全部通过。
- 未执行任何浏览器旅程、未启动产品运行时、未修改 candidate 或 protected refs、未合并或部署。
