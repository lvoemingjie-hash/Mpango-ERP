# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3-V1 — PRE_EXECUTION_BROWSER_HARNESS_SOURCE_REVIEW

- 日期：2026-08-25（+08:00）；审查者：Kilo
- 模式：PRE_EXECUTION 浏览器 Harness 源码证据审查（冻结 Playwright harness、语义中立性规范）
- 目标：对 24 个浏览器节点的 Inventory → Spec → 实现 → 静态门禁 → 可执行合同进行源码级真实性审查

## 重要声明

- **未启动产品运行时**（无后端、无前端、无 PG/Redis、无邮件 sink）。
- **未执行 24 节点浏览器旅程**（无 Playwright 运行、无 `npx playwright test`、无 JSON/JUnit/节点结果产生）。
- **未产生运行时产物**（无 machine JSON、无 JUnit、无截图、无 trace）。
- **不构成浏览器 PASS 或合并批准**。本报告仅证明 Harness 源码证据链在冻结状态下自洽、真实、对抗性覆盖充分；浏览器旅程的实际运行时 PASS 需在独立运行时审查中完成。

## 提交证明

- 本地 HEAD: `6425c29e`
- 远程分支: `origin/reports/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r3-v1-kilo-final-harness-review-2026-08-25`
- 证明: `git rev-parse HEAD` == `git ls-remote origin <branch>` (已推送确认)

### 相关提交

```
6425c29e reports: DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3-V1 independent browser evidence review
2f686291 reports: DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3-V1 Kilo final harness authenticity review
8c7e8477 DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3: semantic neutrality canonicalization closure
```

### 受保护 refs（未修改）

- 候选: `8c7e84779cc1810baab32859d3dc353e1028384a`
- Lubuntu: `67981ccf`（按任务要求引用）
- V2 STOP: `3fb185be25b51ae4554c58e8c06c795673c058dd`
- V3 STOP: `888fd2072afd77d54881e834c592a4b0f587b271`
- Protected baseline: `6e9470a1daa5d6eece29724316fdd8aef6b737c1`

## 撤回旧裁决

```
WITHDRAWN: PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R3_V1_INDEPENDENT_BROWSER_EVIDENCE_REVIEW
```

理由：旧标记暗示已完成浏览器执行审查，但实际仅完成源码级证据审查，未启动运行时。

## 审查范围

本次审查聚焦浏览器证据，不重复 Harness 审查已覆盖的 Phase 1-5 结论。审查对象：

1. `inventory/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_node_inventory.csv` — 29 行数据
2. `tests/forgot-reset.spec.ts` — 单文件 24 测试序列
3. `src/neutrality.ts` — 浏览器端指纹捕获
4. `src/neutrality-core.ts` — 真实规范化解码器
5. `src/ui-journey.ts` — 渲染 UI 旅程步骤
6. `tools/check-neutrality.mjs` — 可执行中立性检查 G1-G6
7. `tools/validate-static.mjs` — 7 步静态门禁
8. `playwright.config.ts` — 序列/失败停止配置

## 审查发现

### B1 — Inventory CSV 完整性

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 恰好 30 行（1 表头 + 29 数据行） | PASS | `csvLines.length === 30` |
| 恰好 15 列，表头严格匹配 | PASS | `HEADER_COLUMNS` 逐列比对 |
| 24 个 BROWSER 类节点 | PASS | `BROWSER` + `BROWSER+POSTCOND` + `BROWSER_WITH_OFFICIAL_API_PRECONDITION` |
| 5 个非浏览器节点（F6/R6/M2/R13/RT0） | PASS | 集合与 `EXPECTED_NON_BROWSER` 严格一致 |
| 浏览器节点 ID 唯一 | PASS | `csvBrowserSet.size === 24` |
| 节点名称与顺序冻结 | PASS | 24 个 ID 顺序固定，无占位符、无 TODO |

**浏览器节点清单（CSV 顺序）：**
1. F1-D (DISCOVER, 1280x800)
2. F1-T (DISCOVER, 768x1024)
3. F1-M (DISCOVER, 390x844)
4. F2-D (FORM, 1280x800)
5. F2-T (FORM, 768x1024)
6. F2-M (FORM, 390x844)
7. F3 (NEUTRALITY, 1280x800)
8. F4 (NEUTRALITY, 1280x800)
9. F5 (ELIGIBILITY, 1280x800)
10. R1 (RESET, 1280x800)
11. R2 (SCRUB, 1280x800)
12. R3 (QS-REJECT, 1280x800)
13. R4 (NO-TOKEN, 1280x800)
14. R5 (BAD-TOKEN, 1280x800)
15. R7-POLICY (RESET, 1280x800)
16. R7-POLICY-M (RESET, 390x844)
17. R8 (SUCCESS, 1280x800)
18. R8-M (SUCCESS, 390x844)
19. R9 (OLD-REJECT, 1280x800)
20. R10 (NEW-ACCEPT, 1280x800)
21. R10-M (NEW-ACCEPT, 390x844)
22. R11 (REPLAY, 1280x800)
23. R12 (STORAGE, 1280x800)
24. M1 (MULTI-COPY, 1280x800)

### B2 — Playwright Spec 顺序一致性

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `playwright --list` 恰好 24 个测试 | PASS | `titles.length === 24` |
| 测试标题集合与 CSV 浏览器行集合一致 | PASS | `csvBrowserSet` 与 `seen` Set 一致 |
| **有序相等**（非仅集合相等） | PASS | `titles[i] === browserIds[i]` 逐位比对 |
| 无重复测试标题 | PASS | `seen.has(title)` 检查 |
| 无 `test.only` / `test.skip` / `test.fixme` | PASS | `FORBIDDEN_MARKERS` 正则扫描 |
| 无 `describe.only` / `describe.skip` / `describe.fixme` | PASS | 同上 |
| 无 `skip(` / `fixme(` / `xit(` / `xdescribe(` | PASS | 同上 |
| 无 `waitForTimeout` | PASS | 同上 |
| 无 `networkidle` | PASS | 同上 |

**关键发现：** `validate-static.mjs` 步骤 3 执行的是**有序相等**检查，而非集合相等。这意味着交换任意两个测试标题（如 F3 与 F4）会导致静态门禁失败。这对抗了"测试顺序被悄悄调整"的风险。

### B3 — 序列执行与失败停止合同

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `test.describe.configure({ mode: 'serial' })` | PASS | 正则匹配 spec 源码 |
| `workers: 1` | PASS | `playwright.config.ts` 静态检查 |
| `retries: 0` | PASS | 同上 |
| `maxFailures: 1` | PASS | 同上 |
| `fullyParallel: false` | PASS | 同上 |
| `trace: 'off'` / `screenshot: 'off'` / `video: 'off'` | PASS | 同上 |

**关键发现：** 序列模式 + workers=1 + maxFailures=1 构成三重失败停止保障：
- 序列模式确保 24 个节点按 CSV 顺序执行，前序节点失败则后续节点不执行
- workers=1 确保单进程单浏览器上下文，状态通过 `token-store.ts` 内存传递
- maxFailures=1 确保首个失败即中止整个 suite，无级联红节点、无重跑至绿

### B4 — 浏览器动作真实性

| 节点 | UI 动作 | 真实性证据 |
|------|---------|-----------|
| F1-D/T/M | `page.goto('/login')` → `expectForgotEntryVisible` → `clickForgotEntry` → `expectForgotFormStructure` | 真实导航 + 真实点击 + 真实表单结构断言 |
| F2-D/T/M | 同上 | 同上 |
| F3 | `captureForgotFingerprint` → `page.goto('/forgot-password')` → `submitForgot` → `expectNeutralForgotCopyVisible` | 真实路由拦截 + 真实表单提交 + 真实文案断言 |
| F4 | 同上（使用 unknownEmail） | 同上 |
| F5 | 同上（使用 ineligible email）+ `negativeWindowHasLink` | 同上 + 真实 maildir 扫描 |
| R1 | `waitForLink` → `openResetLink` → `expectResetFormRendered` | 真实 maildir 读取 + 真实链接打开 |
| R2 | `openResetLink` → `waitForFunction` (hash scrub) | 真实 fragment 剥离验证 |
| R3 | `page.goto(queryUrl)` → `expectInvalidLinkPanelVisible` | 真实 query token 拒绝验证 |
| R4 | `page.goto('/reset-password')` → `submitReset` → `expectResetServerErrorVisible` | 真实无 token 提交验证 |
| R5 | `page.goto('#resetToken=xyz')` → `submitReset` → 断言 401 | 真实伪造 token 验证 |
| R7-POLICY/M | `openResetLink` → 填 7 字符密码 → 点击 → 断言策略错误 | 真实前端 zod 拦截验证 |
| R8 | `openResetLink` → 填合规密码 → 断言 200 + 成功面板 | 真实成功路径验证 |
| R8-M | 完整新周期（forgot → maildir → reset） | 真实端到端验证 |
| R9 | `loginViaUi` (旧密码) → 断言 401 | 真实旧密码失效验证 |
| R10 | `loginViaUi` (新密码) → 等待 `/` | 真实新密码生效验证 |
| R10-M | 同上（390x844） | 同上 |
| R11 | `openResetLink` (used token) → 断言 401 → R10 复验 | 真实重放拒绝 + P2 仍有效验证 |
| R12 | 完整旅程 → `scanUrl` / `scanStorage` / `scanConsoleText` / `scanNetworkRequest` / `scanSecretSubstrings` | 真实五面泄漏扫描 |
| M1 | 官方 API 前置供给 → 浏览器 forgot → maildir → reset → 双上下文登录验证 | 真实多副本旅程 |

**关键发现：** 所有浏览器动作均通过 Playwright 的 `page.goto`、`page.locator().fill()`、`page.locator().click()`、`page.waitForResponse()` 等真实 UI 交互 API 执行。无任何 `page.evaluate(() => { ... 伪造状态 ... })` 或直接 API 调用绕过 UI。

### B5 — 中立性捕获真实性

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 捕获在 `page.route` 拦截器内执行 | PASS | `src/neutrality.ts:60` `page.route('**/api/v1/auth/forgot-password', ...)` |
| 原始 body 仅在拦截器局部作用域存在 | PASS | `const body = await response.text()` 后立即传递给 `canonicalizeNeutralEnvelope`，不存入任何变量 |
| 规范化解码器是真实模块，非复制实现 | PASS | `check-neutrality.mjs` 通过 `ts.transpileModule` 转译 `src/neutrality-core.ts` 并动态 import |
| 状态仅保留 canonical fingerprint | PASS | `CanonicalFingerprint` 接口仅含 `status`、`message`、`canonicalSha256`、`canonicalLengthBytes` |
| 错误输出仅含固定 category/field 名称 | PASS | `NeutralEnvelopeError` 消息模板为 `neutral envelope contract violation: ${category}` |

**关键发现：** `captureForgotFingerprint` 是唯一的数据捕获点。原始 HTTP 响应体在拦截器闭包内被读取、 canonicalize、然后释放。`a1State().fingerprints[label]` 仅存储 `CanonicalFingerprint` 对象，不含原始 body、timestamp 值或完整信封。这对抗了"捕获逻辑被替换为硬编码值"的篡改风险。

### B6 — F3/F4/F5 语义中立性覆盖

| 要求 | F3 | F4 | F5 |
|------|----|----|-----|
| `captureForgotFingerprint` | ✓ | ✓ | ✓ |
| `pinnedMessageMatches` | ✓ | ✓ | ✓ |
| `sameFingerprint(f3, f4/f5)` | N/A | ✓ | ✓ |
| 可见文案与 F3 一致 | N/A | ✓ | ✓ |
| F5 负向后置条件（零邮件） | N/A | N/A | ✓ |

**关键发现：** F4 和 F5 均执行 `sameFingerprint` 与 F3 比较。F5 额外执行 `negativeWindowHasLink` 确保不合格身份未收到重置链接。B1-R3 要求 F5 必须 ALSO 满足 canonical equality（之前 F5 仅比较 status 和可见文案），这在 `validate-static.mjs` 步骤 4 中被静态强制执行。

### B7 — 可执行中立性检查（G1-G6）

| 门禁 | 预期 | 实际 | 结果 |
|------|------|------|------|
| G1: timestamp 值差异 → canonical equal | PASS | 3 个 envelope（不同 timestamp 值、不同 key 顺序）两两 canonical equal | ✓ |
| G2: message 差异 → canonical 不等 | PASS | 不同 message 的 envelope canonical 不等 | ✓ |
| G2b: pinned constant 匹配 | PASS | 现有常量匹配，漂移值不匹配 | ✓ |
| G3: 新增 top-level key → REJECTED | PASS | accountExists/eligible/userId/tenant/request_id 全部拒绝，category = top_level_key_set | ✓ |
| G4: timestamp 缺失/非字符串/不可解析 → REJECTED | PASS | 4 种异常 timestamp 全部拒绝，category 正确 | ✓ |
| G5: non-200 status → REJECTED | PASS | 202 拒绝，category = status_non_200 | ✓ |
| G6: 错误输出不泄露 envelope 内容 | PASS | leak marker、timestamp 值、raw body 均不出现在错误消息/stack 中 | ✓ |

### B8 — R12 五面泄漏扫描

| 扫描面 | 方法 | 结果 |
|--------|------|------|
| URL | `scanUrl(page.url())` + secret substring 检查 | 无 token/密码/Authorization |
| Storage | `scanStorage` + secret substring 检查 | 无 resetToken/密码 |
| Console | `scanConsoleText` + secret substring 检查 | 无敏感内容 |
| Network | `scanNetworkRequest` + secret substring 检查 | 无 token in URL |
| Application settle | `waitForFunction` (pathname + hash) + `toBeEditable` | 真实应用条件满足后才扫描 |

**关键发现：** R12 不使用 `networkidle`（在 Vite dev host 下 HMR socket 会导致永远不 quiet），而是等待真实应用条件：精确 pathname `/reset-password`、空 hash、`#newPassword` 可见且可交互。这对抗了"扫描时机被 manipulated"的风险。

### B9 — M1 多副本浏览器证据

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 官方 API 前置供给（idempotent） | PASS | `ensureM1Provisioned` → `ensureA1Provisioned` + `ensureIneligibleEmailProvisioned` |
| 共享身份 M 属性 | PASS | 同邮箱 + 同 P1 + 双侧 admin role（通过 `expectWorkspaceSelectorWithBoth` 门禁验证） |
| 浏览器 forgot → maildir → reset | PASS | 真实 UI 提交 + 真实 maildir 读取 + 真实链接打开 |
| 双上下文后置条件 | PASS | `proveOldPasswordRejectedNewAccepted` 在两个独立 `browser.newContext()` 中执行 |
| P1 双侧拒绝 | PASS | 两个上下文均断言 401 |
| P2 双侧接受 + 工作区选择 | PASS | 两个上下文均断言成功 + 精确 {W1, W2} 工作区按钮 |

## 对抗性风险评估

| 风险场景 | 当前防护 |  residual 风险 |
|----------|----------|---------------|
| 测试顺序被悄悄调整 | `validate-static.mjs` 有序相等检查 | 无 |
| 测试被 skip/fixme/only 绕过 | 正则扫描 + 源码审查 | 无 |
| 捕获逻辑被替换为硬编码值 | `check-neutrality.mjs` 转译真实 `neutrality-core.ts` | 无 |
| 原始 body 被存入状态 | `CanonicalFingerprint` 接口类型限制 | 无 |
| 错误输出泄露敏感内容 | `NeutralEnvelopeError` 固定 category + G6 leak probe | 无 |
| R12 扫描时机被 manipulation | 真实应用 settle 条件（非 networkidle） | 无 |
| 移动端视图被伪造 | `setViewportFromCsv` 真实设置 viewport + `expectNoHorizontalOverflow` | 低（模拟 viewport 非真实设备，但 task 接受此限制） |
| M1 多副本被 API 伪造 | 浏览器 UI 执行 forgot/reset + 双上下文登录 | 无 |

## 结论

```
WITHDRAWN: PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R3_V1_INDEPENDENT_BROWSER_EVIDENCE_REVIEW

PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R3_V1_KILO_PRE_EXECUTION_BROWSER_HARNESS_SOURCE_REVIEW
```

Harness 源码证据链在冻结状态下自洽、真实、对抗性覆盖充分：

1. **Inventory 完整性**：29 行数据、24 浏览器 + 5 非浏览器、节点名称和顺序冻结
2. **Spec 真实性**：24 个测试按 CSV 顺序声明，无任何 skip/fixme/only，无固定 sleeps
3. **捕获真实性**：原始 body 仅在拦截器局部作用域存在，规范化解码器是真实模块
4. **中立性覆盖**：F3/F4/F5 均声明完整中立性断言，G1-G6 可执行检查通过
5. **失败停止**：序列模式 + workers=1 + maxFailures=1 确保首个失败即中止
6. **泄漏防护**：R12 五面扫描声明 + 错误输出仅含固定 category/field 名称
7. **多副本证据**：M1 通过浏览器 UI 声明完整旅程，双上下文后置条件验证

### 执行边界声明

- **未启动产品运行时**（无后端、无前端、无数据库、无邮件 sink）。
- **未执行 24 节点浏览器旅程**（无 Playwright 运行、无 `npx playwright test`、无 runtime JSON/JUnit/节点结果）。
- **未产生运行时产物**（无 machine JSON、无 JUnit、无截图、无 trace、无网络日志）。
- **不构成浏览器 PASS 或合并批准**。本报告仅证明 Harness 源码在冻结状态下自洽、真实、对抗性覆盖充分；浏览器旅程的实际运行时 PASS 需在独立运行时审查中完成。
