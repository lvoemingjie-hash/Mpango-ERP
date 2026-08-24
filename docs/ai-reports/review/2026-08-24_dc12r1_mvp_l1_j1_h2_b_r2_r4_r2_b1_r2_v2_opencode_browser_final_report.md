# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R2-V2 — OpenCode 独立全新运行时浏览器终验报告

- 任务代号: DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R2-V2 (opencode-browser-final)
- 日期: 2026-08-24 (UTC)
- 执行方: OpenCode (ZCode 授权浏览器终验)
- **裁决: `STOP_AND_REPORT_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R2_V2_OPENCODE_BROWSER_FINAL`**
  （未达成 `PASS_FOR_CTO_...`。权威运行在 F3 首红即停：6 passed / 1 failed /
  17 did not run。根因为**任务启动器供给的身份邮箱域** `.invalid` 属特殊保留域，
  被产品后端 EmailStr 校验正确拒绝（422）；产品与冻结 harness 均无缺陷。按协议
  未重跑、未重置数据。）

## 0. 冻结引用（运行前后均未变，快照见 evidence/frozen-refs-{start,end}.txt）

| 引用 | SHA |
|---|---|
| PRODUCT_SOURCE | `8c462170804322d3f73803d8991c00879582e232` |
| HARNESS | `cb35207969fc1b0c8d8488ac65d75e47fedc3f23` |
| KILO_REVIEW | `1082f6177af69ce57c1951e07009d0a13f0e2400` |
| LUBUNTU_REVIEW_BRANCH_TIP | `9066e1171f55177a2362788ac22788a76d68d066` |
| BACKEND_ZERO_RED | `5570093ec7f9e3dc2b4083ac8c091aae75a62d1d` |
| PROTECTED_BASELINE | `6e9470a1daa5d6eece29724316fdd8aef6b737c1` |

## 1. Phase 1 证明门 — 全部 PASS

- `git fetch --all --prune` 完成。
- HARNESS == 远端候选分支 `origin/zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r2-app-settle-eol-portability-2026-08-24` tip；`HARNESS^ == e65e9a7f61c78906c2c5874d6589d4bada23942c`。
- PRODUCT_SOURCE 是 HARNESS 祖先（merge-base --is-ancestor 通过）。
- detached worktree 精确检出 HARNESS，`git status --porcelain` 为空。
- `git diff --name-only PRODUCT_SOURCE HARNESS`：22 个新增文件**全部**位于 `j1h2b-forgot-reset/`，产品路径（backend/**、frontend/** 及其余）树级字节一致（0 处外部变化）。
- Harness 恰好 22 个 tracked 文件；worktree clean。

## 2. Phase 2 全新独占运行时 — 全部 PASS

- 独占容器 `j1h2b-v2-pg16`（postgres:16-alpine）与 `j1h2b-v2-redis7`（redis:7-alpine）；独占卷 `j1h2b-v2-pgdata`、`j1h2b-v2-redisdata`；独占网络 `j1h2b-v2-net`；宿主上既有容器（mpango_* 等）一律未触碰。
- 端口预先确认空闲后使用：PG 127.0.0.1:55432、Redis 127.0.0.1:56379、backend 127.0.0.1:8000、frontend 127.0.0.1:5173；全部仅绑定回环。
- 空库 `mpango_erp`（迁移前 `\dt` 无任何表）→ `alembic upgrade head` → `alembic current` = `037_payment_declarations_schema (head)`，唯一 head（28 个 revision、1 个 head）。
- 后端经生产入口 `backend/main.py`（uvicorn 承载 `main:app`），`MPANGO_ENV=staging`，真实 JWT（任务专属随机 SECRET_KEY，64 字符，值从未打印/提交/入证据）；任务私有启动器仅承担 README 记载的 maildir sink 落盘职责（无新增 HTTP 面、无 SQL/ORM）。
- 前端为 **Vite dev host**（`vite --host 127.0.0.1 --port 5173 --strictPort`，HMR 运行时，正是 B1-R2 修复的验证目标）；`/api` 代理连通后端验证通过。
- 任务专属 maildir（初始为空）；不复用任何旧数据库/身份/maildir/token/容器/卷。

## 3. Phase 3 冻结 Harness 前置门 — 全部 PASS（harness 目录内）

| 门 | 结果 |
|---|---|
| `pnpm install --frozen-lockfile` | PASS（@playwright/test 1.49.1 / @types/node 22.10.5 / typescript 5.7.3 精确锁定） |
| `pnpm exec playwright test --list` | PASS — 恰好 24 tests / 1 spec，顺序与 CSV 浏览器行完全一致（F1-D…M1） |
| `node tools/validate-static.mjs` | PASS — 6/6（CSV 29×15 与 24/5、registry 交叉、有序 list 相等、serial/maxFailures:1/无固定等待/R12 app-settle 三条件/无 networkidle、.gitattributes LF、22 文件严格 UTF-8 无 BOM 无 CR） |
| `pnpm exec tsc --noEmit` | PASS — 零诊断 |
| `git diff --check`（worktree） | PASS |
| detect-secrets | PASS — 21 个 tracked harness 源文件 0 发现；pnpm-lock.yaml 仅 7 处 sha512 integrity 哈希误报（与冻结时同况）；node_modules 内 84 处为第三方内容（untracked） |

workers=1、retries=0、maxFailures=1、单一 serial describe 由冻结 config 与校验器第 4 步共同确认；24 browser + 5 non-browser = 29（校验器第 1/2 步）。凭据仅按冻结 README 的 J1H2B_* 合同在运行时供给。

运行前健康三检查：`/health`、`/health/ready`、`/health/live` 均 200；frontend `/`、`/login` 200。PB-1 只读复核：AppRouter 仍无 `retailer/forgot-password`、`retailerForgotPassword` 在 .tsx 中零调用 → **RT0 维持 `BLOCKED_BY_H2_C`，未尝试亦不允许任何 API 绕过。**

## 4. Phase 4 供给边界 — 合同遵守（供给在权威运行内、按需、全部正式 API）

全部供给由冻结 harness 在单次权威运行内按需执行且仅用正式生命周期/API：
- A1: signup(202) → maildir 验证链接（浏览器外私有读）→ verify-email(200) → setup-credential(200) → login → select-tenant；
- X（不合格邮箱）: 正式 `POST /api/v1/users`(201) + 正式软删除 `DELETE /api/v1/users/{id}`；
- M1: W1/W2 owner 不同邮箱各自正式生命周期；M 同一规范化邮箱、两侧同一初始密码 P1、经正式 `POST /api/v1/users` 创建、经正式 `PUT /users/{id}/roles` 双侧 admin role；前置门断言 M 登录精确见 W1/W2（计数与名称，值不回显）。

无 SQL/直连 ORM/手写哈希/debug 端点/数据库修补/旧身份复用；API 供给不替代任何 forgot/reset 浏览器旅程动作。凭据只存在于任务进程环境（22 个 J1H2B_* 变量，6 个互异邮箱、8 个 ≥8 字符密码、distinctness 规则校验通过，值从未打印）。

**供给前静态尽职核验（本任务追加，只读）**：harness UI_COPY 全部锚点与冻结前端源码逐一匹配（LoginPage.tsx:213 "Forgot password?"、ForgotPasswordPage.tsx:14 中性文案、ResetPasswordPage.tsx #newPassword/"Invalid Link"/"Request new link"/成功面板、WorkspaceSelectorPage "Welcome Back" 按租户名渲染）；供给端点状态码契约（signup 202、users 201、roles 200）与后端源码一致。

## 5. Phase 5 唯一权威运行 — 两次调用全披露，F3 首红即停

### 5.1 调用 #1（中止于 fail-closed 门，非旅程结果）

UTC 2026-08-24T15:42:42Z。任务私有 env 文件中含空格值（worktree 路径 `MPANGO ERP` 与公司名）**未加引号**，source 时被拆断 → harness fail-closed 门（src/env.ts requireAll）在 beforeAll、**任何旅程动作之前**拒绝运行：F1-D 0ms 报缺失变量名（仅名称），23 个未运行，maxFailures:1 即刻停止。中止后 pristine 证明：tenant_registrations=0、password_reset_tokens=0、tenant schema=0、maildir 0 文件。归类：**启动器前置门缺陷**（README 明文 "Missing variables fail the run before any journey action"）。原始证据保全于 evidence/aborted-invocation-1/。

### 5.2 调用 #2 = 权威运行（2026-08-24T15:45:44Z 起，完整命令恰一次）

`Running 24 tests using 1 worker`。结果：

- **6 passed（3.9s）**: F1-D / F1-T / F1-M / F2-D / F2-T / F2-M — 真实产品 UI 在 **Vite dev host（HMR 运行时）** 下、三个 CSV 视口（1280×800 / 768×1024 / 390×844）全部通过：忘记密码入口发现、可达 /forgot-password、表单结构、390px 无横向溢出。
- **1 failed: F3** — 失败点在节点内的**正式 API 供给前置**（ensureA1Provisioned → `POST /api/v1/auth/signup` 返回 422 而非 202），F3 的浏览器旅程动作（打开忘记页、提交 A1 邮箱、中性文案断言、指纹采集）**尚未发生**。净化错误仅含状态码与端点名（无邮箱值）。
- **17 did not run**（maxFailures:1 fail-stop 如约生效；stats: expected 6 / unexpected 1 / skipped 17 / flaky 0 / interrupted 0）。
- 运行后 DB/maildir 仍 pristine（registrations=0、reset_tokens=0、maildir 0）——422 拒绝未创建任何状态。

### 5.3 根因（只读诊断，链完整）

启动器生成的身份邮箱使用特殊保留域 `@j1h2b-task.invalid`。产品后端 pydantic EmailStr（email-validator）按产品设计**正确拒绝**特殊保留域：`The part after the @-sign is a special-use or reserved name that cannot be used with email` → 422 VALIDATION_ERROR（后端日志，任务私有）。harness env.ts 的 EMAIL_PATTERN 为语法级（接受该域），与产品更严的语义级校验存在合同落差——**任务域的选择由协议留给任务方**（"persona-*@任务域"），本启动器选域错误。

责任归属：**任务启动器（供给凭据构造）缺陷**。产品行为正确（拒绝保留域是应有的输入校验）；冻结 harness 行为正确（fail-closed、净化错误、maxFailures:1 fail-stop、单次运行纪律）。无产品缺陷、无 harness 缺陷、无秘密泄漏。

### 5.4 协议遵守声明

首红即停：未修改任何文件刷绿、未重置数据、未执行第二次完整运行（调用 #1 中止于旅程开始前的 fail-closed 门并全披露；调用 #2 为唯一权威运行）。无 grep/shard/retry/repeat-each。R12 未达（在其之前的 F3 停止），故 B1-R2 的 app-settle 条件本次未经浏览器验证——这是 V3 待验证项，不是本次缺陷。

## 6. Phase 6 对账与秘密边界

- 原始 Playwright JSON 与 JUnit：evidence/authoritative-run/results.json、results-junit.xml（stats: 6/1/17, duration 3.93s）。
- 24 行节点结果 CSV（node-results.csv）与 test-list.txt：6 passed / 1 failed(F3) / 17 skipped(did-not-run)。
- reconciliation.json：**29 节点对账 gap=0**（24 browser + 5 non-browser）。非浏览器结果：R13 已执行 PASS（scan-artifacts 3 文件零发现，含 --secrets-from-env 对 8 个运行密码的字节匹配）；F6 NOT_REACHED（F3 停止前无任何邮件事件，maildir 0 文件）；R6/M2 维持 `BACKEND_PRE_GATE_ONLY`，引用已接受后端前置证据 `5570093e`（Lubuntu dual fresh-stack zero-red final），不计浏览器 PASS；RT0 维持 `BLOCKED_BY_H2_C`。
- failure_set.json：F3 failed + 17 skipped 全列。
- provisioning/runtime preflight：evidence/preflight.md。
- R13 产物扫描：PASS（evidence/authoritative-run/r13-scan.txt）。
- 证据目录泄漏扫描（清理前带值匹配 8 密码+SECRET_KEY+REPORTING_USER_PASSWORD，与清理后终态结构扫描）：**0 发现**（leak-scan-evidence-dir.txt）。trace/screenshot/video 全程 off 且无任何图像/视频/trace 产物（R13 同步强制）。
- committed-blob SHA-256 manifest：22 文件 git blob SHA-1 + 内容 SHA-256（committed-blob-manifest.csv，基线 cb352079）。
- 证据不含密码/JWT/Authorization/SECRET_KEY/邮件 token/maildir 原文/环境文件/trace/截图/视频。

## 7. Phase 7 清理与发布

清理闭包见 evidence/cleanup.md：任务进程终止；端口 8000/5173/55432/56379 全部释放；容器/卷/网络零残留；maildir、凭据（task.env / j1h2b-run.env）、任务日志、venv、worktree 全部删除；既有宿主容器未触碰；六个冻结 refs 运行前后逐字相同（frozen-refs-start.txt == frozen-refs-end.txt）。本报告分支基于 HARNESS cb352079。

## 8. 裁决与下一步

**`STOP_AND_REPORT_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R2_V2_OPENCODE_BROWSER_FINAL`**

- 目标裁决 `PASS_FOR_CTO_..._OPENCODE_BROWSER_FINAL` **未达成**（24/24 未获；F3 首红）。
- 真实部分结果：6/24 浏览器节点通过（F1/F2 全视口，Vite dev host 下）；产品与 harness 无缺陷发现。
- 唯一根因：启动器身份域选择（特殊保留域）触发产品正确拒绝。**修复面在任务供给侧**（改用非保留域的任务邮箱域），不在产品/harness。
- 供 CTO 决策的 V3 建议（如授权）：(1) 供给域改为非 special-use 域（email-validator 可接受，如真实 TLD 下的任务子域）；(2) 可选加固：harness env.ts 对身份域增加与产品一致的保留域拒绝（属 harness 变更，需重新冻结/审查，非本次范围）；(3) V3 全新运行时+全新身份+全部门禁重跑。
- 即使 V3 全绿，仍不得合并/部署/启动 H2-C；下一步仅为 Kilo 证据审查，再由 CTO 决定受控合并。RT0/PB-1 仍待 H2-C。
