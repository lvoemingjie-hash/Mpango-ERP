# FROZEN REPORT — DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3

> ## B1-R3 附录 — Semantic Neutrality Canonicalization Closure（2026-08-25）
>
> Parent: `cb35207969fc1b0c8d8488ac65d75e47fedc3f23`（B1-R2）。
> Branch: `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r3-semantic-neutrality-canonicalization-2026-08-25`。
> 授权范围：仅 `j1h2b-forgot-reset/**`；产品路径相对 `8c462170` 字节不变；
> 不删除/固定/修改产品 timestamp；不加依赖；不改 package.json/lockfile。
>
> CTO 裁决输入：V3 STOP `888fd2072afd77d54881e834c592a4b0f587b271`（F4
> bodySha256 差异真实、仅源于平台通用逐请求顶层 timestamp、非枚举信号、
> 旧 raw-byte equality 属过度约束）。V2 STOP `3fb185be` 原样保留。
>
> 变更（22 → 25 文件，详见 R4-NEUTRALITY-PROTOCOL-CORRECTION.md）：
> 1. 新增 `src/neutrality-core.ts`：真实 canonicalizer（依赖仅 node:crypto）——
>    精确顶层 key 集 `{success,data,message,timestamp}`、success===true、
>    data==={}、message 类型校验 + 钉住产品中性常量谓词
>    `pinnedMessageMatches`、timestamp 存在/字符串/可解析校验、顶层
>    timestamp 值→固定 sentinel 替换、稳定序列化 SHA-256+长度；错误仅
>    固定类别。禁通用 key 删除器/正则黑名单/递归忽略（validator 静态禁
>    `delete`/`filter(` 于 core）。
> 2. `src/neutrality.ts`：capture 在路由 handler 局部作用域解析原始 body
>    并即刻释放，仅存 canonical fingerprint。
> 3. `tests/forgot-reset.spec.ts`：F4 文案改 canonical；**F5 新增与 F3 的
>    canonical 相等断言**；F3/F4/F5 各新增 pinnedMessageMatches 断言。
> 4. 新增 `tools/check-neutrality.mjs`：可执行中性合同检查 G1–G6（用已装
>    typescript 转译真实 core 后执行夹具矩阵）。
> 5. `tools/validate-static.mjs`：第 4 步扩展 F3/F4/F5 spec 合同（F5
>    canonical 相等与 pinned 谓词存在性）与 core 合同面；新增第 7 步执行
>    可执行中性检查（7/7）。
> 6. inventory CSV：仅 F3/F4/F5 的 expected_http/security_assertion/notes
>    列更新为 canonical 合同；节点 id/class/数量/顺序不变（24+5=29）。
>
> 变异真值门 M1–M6：全部先 RED 后恢复 GREEN（M1 raw-sha 恢复、M2 删
> canonical payload 的 message、M3 任意 volatile key 放行、M4 跳过
> timestamp 校验、M5 删 F5 canonical 相等、M6 错误泄漏原始 body/timestamp
> 值），每项恢复后候选文件 blob 无漂移。
>
> 不变：24+5=29、节点名与顺序、单一 serial spec、workers=1、retries=0、
> maxFailures=1、trace/screenshot/video off、R12 application-settle 三条件、
> `.gitattributes` LF 合同、依赖与锁文件。
>
> 裁决：`STOP_AND_REPORT_CTO_AWAITING_KILO_AND_LUBUNTU_B1_R3_HARNESS_REVIEW`

> ## B1-R2 附录 — Application Settle And Cross-Host EOL Closure（2026-08-24）【历史保留】
>
> Parent: `e65e9a7f61c78906c2c5874d6589d4bada23942c`（B1-R1）。
> Branch: `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r2-app-settle-eol-portability-2026-08-24`。
> 授权范围（仅 5 个文件）：`tests/forgot-reset.spec.ts`、`tools/validate-static.mjs`、
> `.gitattributes`（新增）、`README.md`、`FROZEN-REPORT.md`。
>
> 审查处置：
> - **Kilo PASS（B1-R1 有界审查）标记为
>   `SUPERSEDED_BY_B1_R2_SETTLE_AND_EOL_PORTABILITY_CLOSURE`**。依据其自身发现：
>   R12 的通用网络静默等待仅在"无持续 WebSocket/HMR 的运行时"可靠，而冻结协议
>   目标正是 Vite dev 宿主；且网络静默本身不是业务完成条件。
> - **Lubuntu STOP 保留为发现来源**。HMR WebSocket 是否必然使网络无法静默
>   **未经实测**，仅记录为 host-mode-dependent risk——该不确定性本身即足以
>   取消通用网络静默等待作为 settle 条件的资格。
>
> 修复内容：
> 1. R12 删除 `waitForLoadState('networkidle')`，改为真实应用条件：
>    pathname 精确 `/reset-password` + `location.hash === ''`（waitForFunction，
>    15s 有界）+ `#newPassword` 可见且可交互（toBeEditable）；条件满足后立即扫描。
> 2. 新增 harness-local `.gitattributes`：`* text=auto eol=lf`——本目录所有
>    文本文件在任意主机（含 Windows core.autocrlf=true）checkout 均为 LF，
>    消除 Kilo CRLF HOST_LIMITATION 暴露的可移植性缺口。
> 3. `validate-static.mjs`（现为 6 步）主动验证：networkidle 全面禁令（含注释
>    文本）、R12 三条件（pathname/hash/#newPassword 可交互）、`.gitattributes`
>    存在且含 LF 规则且无任何 eol=crlf 规则、既有 no-CR/BOM/固定等待禁令。
>
> 变异真实性门（全部先 RED 后恢复 GREEN）：
> 1. 恢复 networkidle → RED（forbidden marker networkidle）。
> 2. 删除 URL/hash 条件 → RED（R12 must wait for ... pathname/hash）。
> 3. 删除表单可见/可交互条件 → RED（R12 must wait for ... #newPassword）。
> 4. 删除 .gitattributes → RED（must exist）。
> 5. eol=lf 改 eol=crlf → RED（must not contain any eol=crlf rule）。
>
> 文件统计（如实）：B1 新增 26；B1-R1 删除 6 分片 + 新增 1 合并 spec = 21；
> B1-R2 新增 .gitattributes = **22**。24/5/29 对账、单文件 serial、
> maxFailures:1、secret 边界、全部旅程断言、CSV blob（29a2bdd3）、依赖版本
> 均不变；产品目录相对 8c462170 仍零变化。
>
> 裁决：`STOP_AND_REPORT_CTO_AWAITING_FINAL_DUAL_HOST_HARNESS_REVIEW_AND_BROWSER_EXECUTION`

> ## B1-R1 附录 — Global Serial And Fail-Stop Harness Closure（2026-08-24）【历史保留】
>
> Parent: `d123e96da08f10a1976ce2a75d7392039eec0a44`（B1 候选）。
> Branch: `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r1-global-serial-fail-stop-2026-08-24`。
>
> 审查发现修复：
> - P1 全局旅程顺序：6 个分片 spec 合并为唯一 `tests/forgot-reset.spec.ts`，
>   单一外层 `test.describe.configure({ mode: 'serial' })`，节点注册顺序 ==
>   CSV browser 行序（`--list` 有序比较强制）；删除全部文件名排序依赖。
> - P1 首败立即 STOP：`playwright.config.ts` 增加 `maxFailures: 1`（与
>   serial 共同实现"任一失败 ⇒ 全程 STOP"）。
> - P2 固定等待：R2 的 500ms 改为 `waitForFunction`（hash==='' 且
>   pathname==='/reset-password'，15s 有界）+ 精确 URL 断言；R12 的 500ms
>   改为 `waitForLoadState('networkidle', 15s)` 有界沉降后立即扫描。
>
> 变异真实性门（全部先 RED 后恢复 GREEN，validate-static.mjs 主动拦截）：
> 1. 删除 `maxFailures:1` → RED（missing frozen invariant maxFailures: 1）。
> 2. 删除 serial mode → RED（must declare configure serial）。
> 3. 引入第二个 spec → RED（25 tests / 位置 25 漂移 / spec 数）。
> 4. 交换 F3/F4 标题 → RED（position 7: expected F3, found F4）。
> 5. 重新加入固定延时 API → RED（forbidden marker）。
> 校验器同时剥离注释后再验 config/serial 合同（注释化绕过同样 RED）。
>
> 旅程断言、API 边界、24/5/29 inventory、秘密边界、CSV blob、依赖版本
> 全部不变；产品目录相对 8c462170 仍零变化。
>
> 裁决保持：`STOP_AND_REPORT_CTO_AWAITING_KILO_HARNESS_REVIEW_AND_BROWSER_EXECUTION`

- Task: frozen forgot/reset Playwright harness implementation (harness only).
- Parent: `8c462170804322d3f73803d8991c00879582e232`
  (DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2: U6I2 token row identity determinism closure)
- Branch: `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-forgot-reset-playwright-harness-2026-08-24`
- Candidate SHA: recorded in the commit itself and in the task report (a file
  cannot contain its own hash); `candidate^` MUST equal the parent above.
- Accepted evidence chain: protocol `132cf7edaac5d6c57ebcdc2465334f4aa465aab2`,
  Kilo source review `4d42ffcae09d3a362f778c1e0661a72e1147dcba`,
  Lubuntu zero-red `5570093ec7f9e3dc2b4083ac8c091aae75a62d1d`.

## Mode compliance

Harness implemented and frozen ONLY. No product runtime was started (no
backend / frontend / PG / Redis), the authoritative browser journey was NOT
executed, no product source was modified, nothing merged or deployed. The
only executions were `pnpm install --frozen-lockfile` (harness deps in the
harness directory), `playwright test --list`, `tsc --noEmit`, and the pure
static validator.

## File manifest (this commit adds exactly this directory)

```
j1h2b-forgot-reset/.gitignore
j1h2b-forgot-reset/README.md
j1h2b-forgot-reset/FROZEN-REPORT.md
j1h2b-forgot-reset/package.json
j1h2b-forgot-reset/playwright.config.ts
j1h2b-forgot-reset/pnpm-lock.yaml
j1h2b-forgot-reset/tsconfig.json
j1h2b-forgot-reset/inventory/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_node_inventory.csv
j1h2b-forgot-reset/inventory/node-registry.json
j1h2b-forgot-reset/src/api-client.ts
j1h2b-forgot-reset/src/assertions.ts
j1h2b-forgot-reset/src/env.ts
j1h2b-forgot-reset/src/leak-scan.ts
j1h2b-forgot-reset/src/maildir.ts
j1h2b-forgot-reset/src/neutrality.ts
j1h2b-forgot-reset/src/reconciliation.ts
j1h2b-forgot-reset/src/token-store.ts
j1h2b-forgot-reset/src/ui-journey.ts
j1h2b-forgot-reset/tests/01-discover.spec.ts
j1h2b-forgot-reset/tests/02-neutrality.spec.ts
j1h2b-forgot-reset/tests/03-reset-entry.spec.ts
j1h2b-forgot-reset/tests/04-reset-submit.spec.ts
j1h2b-forgot-reset/tests/05-post-reset.spec.ts
j1h2b-forgot-reset/tests/06-multi-tenant.spec.ts
j1h2b-forgot-reset/tools/scan-artifacts.mjs
j1h2b-forgot-reset/tools/validate-static.mjs
```

`node_modules/` and `artifacts/` are gitignored and not committed.

## Inventory reconciliation — 24 / 5 / 29

- Inventory CSV: byte-identical copy of protocol blob
  `29a2bdd30b8ffd9142404dd530486d7fa6fd1f15` (9107 bytes), verified by
  `git hash-object` equality against
  `132cf7ed:docs/ai-reports/test-plans/2026-08-23_..._node_inventory.csv`.
- Strict parse: 30 lines (header + 29 rows), 15 columns per row,
  24 browser-authoritative + 5 non-browser.
- Browser 24 (== `playwright --list` titles, exact set, CSV order):
  F1-D, F1-T, F1-M, F2-D, F2-T, F2-M, F3, F4, F5, R1, R2, R3, R4, R5,
  R7-POLICY, R7-POLICY-M, R8, R8-M, R9, R10, R10-M, R11, R12, M1.
- Non-browser 5 (registry-accounted, NEVER browser PASS):
  F6 (PRECONDITION — maildir helper, in-memory only),
  R6 (BACKEND_PRE_GATE_ONLY), M2 (BACKEND_PRE_GATE_ONLY),
  R13 (POSTCOND — tools/scan-artifacts.mjs after the run),
  RT0 (PROTOCOL_BLOCKER — status BLOCKED_BY_H2_C; no API bypass of the
  missing retailer UI).

## Gate results (freeze-time)

| Gate | Result |
|---|---|
| `pnpm install --frozen-lockfile` (harness dir, PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1) | PASS — @playwright/test 1.49.1 / @types/node 22.10.5 / typescript 5.7.3, exact pins |
| `npx playwright test --list` | PASS — exactly 24 tests in 6 files, titles set-equal to the 24 browser inventory IDs, no duplicates/unregistered nodes |
| `node tools/validate-static.mjs` | PASS — 5/5 steps (CSV 29x15 + 24/5, registry cross-check, list set-equality, forbidden-marker scan + frozen config invariants, strict UTF-8/no-BOM/no-CR over all committed harness files) |
| `npx tsc --noEmit` | PASS — zero diagnostics |
| `git diff --check` | PASS (run at commit time) |
| detect-secrets | PASS (run at commit time; harness scan clean) |
| Product directories vs parent | byte-identical — the commit tree differs from 8c462170 ONLY by the added `j1h2b-forgot-reset/` directory (verified with `git diff --stat` at commit time) |

## Credential and token boundary proof

- All successful-auth credentials come from `J1H2B_*` env vars read at RUN
  time; `loadJourneyEnv` fails closed naming missing VARIABLE NAMES only.
  No credential value exists in any committed file, log line or artifact name.
- The maildir reset link/token is read by `src/maildir.ts` into memory only;
  it is never written to disk, never logged, never captured by trace/
  screenshot/video (all disabled in the frozen config).
- F3/F4/F5 keep only `(status, sha256(body), bodyLength)`; the raw response
  body is discarded at capture time.
- All secret-adjacent assertions go through `assertSan` with field-level
  messages; R12/R13 findings are `surface:field` pairs with values withheld.

## Verdict

`STOP_AND_REPORT_CTO_AWAITING_KILO_HARNESS_REVIEW_AND_BROWSER_EXECUTION`

The only next step after this freeze is the Kilo harness source/authenticity
review. The authoritative browser journey is NOT run by this task.
