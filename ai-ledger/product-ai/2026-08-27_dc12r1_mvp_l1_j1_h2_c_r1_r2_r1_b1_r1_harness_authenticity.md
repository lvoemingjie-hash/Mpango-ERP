# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R1 — Harness Runtime-Oracle Authenticity Closure

- 日期：2026-08-27（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R1（Harness Runtime-Oracle
  Authenticity Closure）
- 验证层级：V1_HARNESS_SOURCE_AND_EXECUTABLE_CONTRACT_CORRECTION；
  CLAIM_CEILING：`HARNESS_FROZEN_AWAITING_KILO_RE_REVIEW`
- BASE：`36f70fb9a074423b585de38e7a7893e80a0eb932`（B1 tip，远端一致）
- KILO_STOP：`c9ffc4aa1a49d8542ff5b79175d849a739d3e686`
  （= `origin/reports/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-b1-v1-kilo-final-harness-review-2026-08-27`
  tip；A–I 共 9 项 STOP：3×假绿、2×假红、DEAD_CODE、FRESHNESS、
  NO_ARTIFACT、SCANNER_SKIP）
- PRODUCT_SOURCE：`bf20e8c9eae620fcf101ded672dfb0afeab937cb`
  （产品树/j1h2b/backend tests 相对此源字节不变，diff 为空）
- 受保护基线：`2c20d58c…`（未漂移）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-b1-r1-harness-authenticity-closure-2026-08-27`
- 授权范围：`j1h2c-retailer-recovery/**` + 本台账；零产品/后端测试/
  j1h2b/迁移/模型/依赖/lockfile 改动；未运行任何产品运行时或真实
  Playwright 旅程。

## 1. Kilo A–I 逐项关闭

- **A（HC12 reset POST 假红→真证明）**：`leak-scan.ts` 重写——reset POST
  的 `reset_token` body 字段是产品合同、不算泄漏（合法豁免）；其余
  一切面（URL/query/storage/console/请求 URL/header/其他 body 字段）
  全扫描。spec HC12：点击**前**装 `waitForRequest`；观测**恰一次**
  reset POST（缺失=超时确定性 RED）；响应 200+成功 UI；JSON body
  精确键集 `new_password,reset_token`；`reset_token` 必须等于内存
  token；w 与额外字段禁止。
- **B（w 完整扫描）**：新增 `scanPublicCode`——API 请求 URL/header/
  body、localStorage/sessionStorage、console 全面扫描；仅允许初始
  fragment 与 canonical `/retail/login?w=`（页面 URL，非 API）。
- **C（真实错误供应商）**：env 新增 `J1H2C_W2_CANONICAL_CODE`
  （fail-closed）；HC09 在**真实 W2** 门户（有效表单）提交 W1 零售商
  email，恰一次 POST；`WRONG${CANONICAL}` 伪造代码被 validator
  [10] 明令禁止（spec-absent 锚）。
- **D（正式供给可达）**：`api-client.ts` 不再是死代码——spec
  beforeAll 调用 `provisionPreconditions`（正式 API 生命周期：W1
  verified/unverified 注册；409 幂等重放接受；其余 fail-closed 只报
  step/field）；PRECONDITION 不计浏览器 PASS；`--list` 仍零 env 可用
  （lazy env）。
- **E（邮件新鲜度）**：`maildir.ts` 重写——提交前 `snapshotDeliveries`
  精确文件集快照；`pollForExactlyOneNewDelivery` 条件轮询恰一个新
  文件（零个=超时 RED，多个=multiple RED；绝不按文件名排序取
  latest）；只解析新文件（杜绝读到 HC06/历史邮件）；
  `parseAndValidateResetLink` 同时支持相对路径与
  PUBLIC_FRONTEND_URL 绝对 URL，精确验证 pathname、空 query、
  fragment 键集 {resetToken,w}、token 非空、canonical w；错误信息仅
  含 step/category（无文件名/邮箱/URL/token/code 值）。
- **F（真实双击）**：`genuineDoubleClickSubmit` 使用 Playwright 真实
  `dblclick()`（完整 actionability 管线）；两个
  `dispatchEvent('click')` 合成输入被 validator [10] 禁止
  （ui-absent 锚）。
- **G（真实响应式）**：HC16 以**新签发**的有效 token+w 打开真实 reset
  表单；`assertInteractiveNoOverflowAt390px` 证明控件可见+可编辑
  （真实 fill+取值验证）且 documentElement 与 body 均无横向溢出；
  无 token 的无效状态页不再可能作为证明（validator G 锚 +
  M17 变异）。
- **H（reconciliation 产物）**：`reconciliation.ts` 新增
  `markPendingAsFailed` + `publishArtifacts`——运行后（无论成败）写
  独立 `artifacts/reconciliation.json`/`.csv`（17 节点逐状态、gap=0
  结构）；失败时如实发布 partial（PENDING→FAIL），绝不预写 PASS；
  afterAll 在 finally 中 `clearMemoryState()`；首个浏览器失败由
  maxFailures=1 先行终止，afterAll 仅发布真实状态，不掩盖；产物仅含
  id/surface/outcome（无 token/密码/邮箱/URL）。
- **I（scanner 权威）**：`package.json` 的 `scan:artifacts` **强制**
  `--secrets-from-env`；scanner 重写——无该标志=FAIL-CLOSED，带标志
  但缺动态 secret 输入（运行密码/reset token env）=FAIL-CLOSED（绝不
  退化为结构扫描）；扫描运行密码、动态 token、Authorization 形状
  （Bearer/Basic 值模式）、canonical w 禁用面 + 既有结构模式；输出
  仅 file/surface/category。

## 2. 新增可执行 runtime-contract 检查

`tools/check-runtime-contracts.mjs`（转译真实模块，fixture 级、无
浏览器/无产品运行时）：
- A：合法 `reset_token` body GREEN；URL/header/其他字段/storage/console
  RED；缺失 reset POST（spec 锚 waitForRequest 先于 click）RED。
- B：w 于 API 请求 URL/header/body/storage/console RED；canonical
  门户 URL GREEN。
- E：stale 邮件拒收（超时）；恰一新投递精确选中；多新投递拒收；
  相对/绝对合法链接 GREEN；错误 pathname/query/缺 w/额外 fragment
  键/错 canonical w RED；错误信息脱敏。
- C：缺 W2 env fail-closed（仅变量名）RED。
- H：partial reconciliation 不得伪装 complete；成功 15+2 通过；
  产物状态如实。
- I：scanner 缺动态 secret 输入 FAIL-CLOSED；缺标志 FAIL-CLOSED；
  输出脱敏。

## 3. 变异门（M1–M19 全 RED + SHA-256 字节恢复 + 恢复后 GREEN）

- M1–M10（B1 保留）在 B1-R1 提交字节上复验：全部 RED + 恢复 OK。
- M11–M19（新增，分别命中 A–I）：
  M11 删 reset POST 观测；M12 禁用 w 扫描断言；M13 伪造 W2；
  M14 删供给调用；M15 删邮件快照（全量替换）；M16 回退合成双击；
  M17 毁 G 锚（裸页证明）；M18 删产物发布；M19 去 --secrets-from-env。
  首轮 M15/M17 NOT-RED 根因（替换后锚点仍残留）已如实定位并改用
  全量替换复验为确定性 RED。每项恢复后与冻结快照 SHA-256 逐位一致。

## 4. 冻结门禁（全部通过）

`pnpm install --frozen-lockfile`；`playwright --list` 15 tests / 1
spec / 顺序一致；validate-static **10/10**（新增 [10] A–I 锚点）；
check-neutrality G1–G6；check-runtime-contracts（A/B/E/C/H/I）；
`tsc --noEmit`；`git diff --check`；scoped pre-commit + detect-secrets
0；全文件严格 UTF-8/no-BOM/no-NUL/LF；GitNexus analyze/status
up-to-date；产品树/backend tests/j1h2b 相对 PRODUCT_SOURCE 字节不变；
变异后候选 tree 无漂移（git status clean）。

## 5. 界限（如实）

- 未运行产品运行时、未执行真实 Playwright 旅程；不声称任何浏览器
  证据或运行时 PASS；HC01–HC17 仍 PENDING_AUTHORITATIVE_RUN。
- B1 历史（README/FROZEN-REPORT/台账）不改写；本台账为唯一事实源。

## 6. 裁决

VERDICT:
**STOP_AND_REPORT_CTO_AWAITING_KILO_H2C_HARNESS_RE_REVIEW**

CLAIM_CEILING：`HARNESS_FROZEN_AWAITING_KILO_RE_REVIEW`。
推送并证明 local == remote、worktree clean（保留供 Kilo）后 STOP。
