# DC-12R1-MVP-L1-J1-H2-B-R2-R3-B0 — Forgot/Reset 浏览器旅程协议冻结

> ## ⚠️ R2 官方租户用户供给真值收窄横幅（2026-08-24，父提交 R1=`48473ed`）
>
> R1 历史全部保留（含 owner signup 唯一性结论与【R1】标注）。R2（分支 `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-b0-r2-official-user-provisioning-truth-2026-08-24`）在其上收窄/恢复以下内容，修正处以【R2】标注：
>
> 1. **结论收窄（不撤回 R1）**：owner signup 不能产生双活跃注册（保留）；**但正式租户本地 `POST /api/v1/users` 可跨两个租户创建同邮箱用户**（`email_exists` 仅查本租户 schema；源码锚点见 §2.5-2）。
> 2. **M1 恢复为 `BROWSER_WITH_OFFICIAL_API_PRECONDITION`**：W1/W2 owner 不同邮箱正式 signup → 各自经正式 API 创建同一 admin 邮箱（必要时 `PUT /users/{id}/roles`）→ 前置门验证登录精确见 W1/W2 → forgot/邮件链接/重置/旧密码拒绝/新密码双租户接受**全部浏览器 UI 执行**。
> 3. 禁止清单不变：SQL/直接 ORM/手写哈希/debug 端点；API 代替 forgot/reset 旅程动作。
> 4. M2 与 R6 维持 `BACKEND_PRE_GATE_ONLY`。
> 5. 统计恢复：**24 browser**（23 个纯 BROWSER/BROWSER+POSTCOND 单副本节点 + M1）+ **5 non-browser**（F6/R6/M2/R13/RT0）= 29。
> 6. signup 中性响应锚点补充 `auth.py:146-154`。
>
> ---
>
> ## ⚠️ R1 供给真值修正横幅（2026-08-24，修正基线 B0=`8b0671c`）【历史保留】
>
> 本文件保留为 B0 历史证据；R1（分支 `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-b0-r1-provisioning-truth-2026-08-23`）就地修正以下内容，修正处以【R1】标注：
>
> 1. **撤回**"官方 signup 允许同一 owner email 创建两个活跃批发商注册"的主张（原 §2.5-2、§4）。冻结源源码证明相反（修正后锚点见 §2.5-2）。
> 2. ~~多副本密码重置路径全部重分类为 `BACKEND_PRE_GATE_ONLY`~~【R2 已按官方用户 API 真值恢复 M1 为浏览器可验证，见 R2 横幅第 2 条】。
> 3. ~~节点统计重算：浏览器权威 23 + 前置/后置/阻断 6 = 29~~【R2 恢复 24/5/29，见 R2 横幅第 5 条】。
> 4. PB-1 保持原文，明确为 **P1 产品阻断，移交后续 H2-C**。
> 5. 未来浏览器范围澄清：批发商受支持 UI 旅程可在运行时验收后执行；零售商旅程冻结至 H2-C。

- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-b0-forgot-reset-browser-protocol-2026-08-23`（B0 原分支）
- 冻结源：`218be690a6d5ad3551c31fa28087964440c888c9`（== 远端源分支 `origin/zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-full-suite-test-hygiene-closure-2026-08-23` HEAD，已核验）
- 保护基线：`origin/product-dev-recovered` == `6e9470a1daa5d6eece29724316fdd8aef6b737c1`（已核验，未触碰）
- Kilo 审批 ref：`b7e67e242fe3e7bdd663e8c5aead2f599c25baa8`（== `origin/reports/dc12r1-mvp-l1-j1-h2-b-r2-r3-v1-kilo-final-review-2026-08-23` HEAD，已核验）
- 模式：**仅文档 + 静态源码映射 + 未来浏览器测试设计。不启动运行时；不实现可执行 Playwright 运行；不修改产品代码/测试/保护 refs。**
- 裁决目标：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R3_B0_BROWSER_PROTOCOL_FREEZE_REVIEW`

---

## 1. Phase 1 — 证明与隔离（已执行，全部只读）

| 项 | 结果 |
|---|---|
| `git fetch --all --prune` | ✅ 完成 |
| 隔离 worktree（新分支自 `218be690`） | ✅ `C:\Users\Jeff0\j1h2b0_worktree` |
| 冻结源 == 远端源分支 | ✅ 两者均为 `218be690` |
| `product-dev-recovered` 未变 | ✅ `6e9470a1` |
| 并行 OpenCode 任务（J1-H2-B-R2-R3-V2）refs 记录 | 远端未见其分支（最近同类为 `...r2-r2-r1-v2-opencode-wsl-dual-fresh-stack-zero-red-final-2026-08-23` = `b4a6e16`）；本地无其 worktree/端口/容器被触碰。**注（2026-08-23 23:38 +08:00 任务中）：委托方通报 OpenCode 因配额受限暂无法完成其部分；本文档与 Playwright 设计由 ZCode 承接（仍不运行、不改产品代码）。** |
| GitNexus | CLI 在位（`gitnexus status` 可用）；该 worktree **未索引**。依"无源文件修改/无工件污染"约束，不执行 `gitnexus analyze`，路由/上下文映射改以直接源码核查完成（本文件 §2 全部锚点）。GitNexus 状态：`NOT_INDEXED_BY_CONSTRAINT` |
| 源文件修改 | 无（授权为零；本任务仅新增 3 个文档文件） |

## 2. Phase 2 — 静态源码真值映射（全部锚点来自冻结源 `218be690`）

### 2.1 前端：发现与表单链

| 环节 | 事实 | 锚点 |
|---|---|---|
| 登录页发现链接 | `Forgot password?` 链接存在 | `frontend/src/pages/auth/LoginPage.tsx:212-213` |
| 忘记密码路由 | `/forgot-password` 公共路由 | `frontend/src/router/AppRouter.tsx:87` |
| 忘记密码表单 | 单字段 email（zod email 校验），中性成功文案固定常量，catch 吞错不泄露 | `frontend/src/pages/auth/ForgotPasswordPage.tsx:8-10,14,27-35` |
| 重置密码路由 | `/reset-password` 公共路由 | `AppRouter.tsx:88` |
| 重置表单 | 单字段 newPassword（zod `min(8)`），**无确认密码字段**（记录：产品无 mismatch 校验，属设计现状而非缺陷） | `frontend/src/pages/auth/ResetPasswordPage.tsx:8-10,118-148` |
| 令牌传输 | **fragment-only**：读 `#resetToken=`；检测到 query 携带敏感参数（resetToken/reset_token/token/newPassword/new_password）即拒页并 `replaceState` 清洗 URL；读取 fragment 后同样清洗 | `ResetPasswordPage.tsx:14-25,34-50`（query 拒绝 35-39；fragment 读取 41-49；清洗 47-49）；公共工具 `frontend/src/utils/urlToken.ts:40-50` |
| query 拒绝 UI | Invalid Link 面板 + Request new link 按钮 | `ResetPasswordPage.tsx:76-97` |
| 成功 UI | 成功面板 + Go to login | `ResetPasswordPage.tsx:110-116` |
| 错误文案 | 服务端错误一律映射为同一句中性文案（invalid or expired） | `ResetPasswordPage.tsx:63-73` |

### 2.2 前端：API 客户端

| 方法 | 契约 | 锚点 |
|---|---|---|
| `forgotPassword` | `POST /auth/forgot-password` body `{email}` | `frontend/src/services/authService.ts:49-50` |
| `resetPassword` | `POST /auth/reset-password` body `{resetToken,newPassword}`（token 仅 body） | `authService.ts:52-53` |
| `retailerForgotPassword` | `POST /client/auth/forgot-password` `{email,wholesalerCode}` | `authService.ts:66-68`（**前端零调用方，见 §4 PB-1**） |
| `retailerResetPassword` | `POST /client/auth/reset-password` | `authService.ts:72-75` |
| API base | `VITE_API_URL || '/api/v1'`（vite 代理到后端） | `frontend/src/services/api.ts:39` |

### 2.3 后端：端点与中性契约

| 端点 | 事实 | 锚点 |
|---|---|---|
| `POST /auth/forgot-password` | 永远中性 200（`NEUTRAL_PASSWORD_RESET_MESSAGE` = "Password reset result is not disclosed through this endpoint."）；存在活跃租户用户才发 1 个 canonical token+邮件；生产 SMTP 不可用则 fail-closed 不提交 token；**H2-B-R0**：内部失败以固定 event_class（SCAN_INCOMPLETE / EMAIL_DELIVERY_NOT_CONFIGURED / UNEXPECTED / SCAN_PARTIAL）+ request_id 记日志与指标，payload 仅计数器/异常类型，**绝不含 email/token/schema**；**H2-B-R1**：扫描不完整（有 schema 失败且未找到用户）抛 `PasswordResetScanIncompleteError`，不再把扫描失败静默当"账户不存在" | `backend/api/v1/auth.py:721-833`（docstring 736-758；SCAN_INCOMPLETE 767-789；DELIVERY 790-808；UNEXPECTED 809-820；PARTIAL 822-833）；`backend/services/password_reset_service.py:61-63` |
| `POST /auth/reset-password` | token 仅 body；query 携带 token/密码 → 直接 401 中性 envelope；**H2-B-R2**：全活跃副本 all-or-nothing 更新（rowcount==1 校验；失败→外层回滚+`PASSWORD_RESET_APPLY_FAILED` 事件+中性 401+token 不标记 used）；无效/过期/已用/已撤销 token 同一中性 401；成功后才标记 `used_at` | `auth.py:837-920+`（query 拒绝 860-876；空 token 877-889；APPLY_FAILED 893-920） |

### 2.4 后端：服务层不变式

| 不变式 | 事实 | 锚点 |
|---|---|---|
| 资格 | 仅"活跃且未删除租户用户"可触发发 token（逐 wholesaler → schema → users 扫描；坏 schema 以 SAVEPOINT 隔离并计数，不再静默） | `password_reset_service.py:172-230` |
| 单活令牌 | 新请求撤销同邮箱全部先前未用令牌（另有唯一部分索引兜底） | `password_reset_service.py:259-273` |
| TTL | `PASSWORD_RESET_TOKEN_TTL = 1 小时` | `password_reset_service.py:61` |
| 存储 | token 行只存 SHA-256(email)（分组）与 hash_token(token)（寻址），**不存明文 email/token** | `password_reset_service.py:159-170,275-286` |
| 一次性 | `with_for_update` 锁行 + `_is_actionable`（非 deleted/used/revoked/过期） | `password_reset_service.py:401-428` |
| 邮件链接 | `/reset-password#resetToken=<urlencoded>`，基于 `PUBLIC_FRONTEND_URL`；**fragment 不入代理访问日志** | `backend/services/onboarding_service.py:444-456` |
| 密码策略 | 前后端一致最小策略：非空且 ≥8 字符 | `onboarding_service.py:105-115`；`ResetPasswordPage.tsx:8-10` |
| 多副本规范 | 同邮箱可跨租户多副本，canonical 同哈希不变式；consume 按邮箱哈希 fan-out | `password_reset_service.py:1-24,305-400` |
| 零售商端点 | `POST /client/auth/forgot-password`（(email, wholesaler_code) 对；仅"已验证且已设密"零售商发 token；中性 200；query token 拒绝）与 `POST /client/auth/reset-password` 存在 | `backend/api/v1/client/auth.py:355-391,393+`；服务 `backend/services/retailer_provisioning_service.py:900-952` |
| 日志边界 | 请求日志仅 route/method/status/latency/request_id 等，不记 body/query；token 邮件构造不落日志 | `backend/api/middleware/request_logging.py:41-82`；`auth.py:737-746` |

### 2.5 显式判定（任务书要求）

1. **旅程适用对象**：批发商 owner/operator —— **完整受支持 UI 旅程**（发现→表单→邮件→重置→复验全链路存在）。零售商 operator —— **发现层缺失**（见 PB-1），重置页 `/retailer/reset-password` 与后端端点存在但无入口到达。故权威旅程作用于批发商侧；零售商侧冻结为协议阻断。
2. **跨租户重复身份能否经受支持生命周期产生**：【R2 收窄 R1 结论·保留 owner signup 唯一性】
   - **owner signup 不能产生双活跃注册**（R1 结论保留）：`_live_registration_for_email` 防止第二个活跃注册（已存在活跃注册时返回 `SignupResult(registration_id=None, status="pending_email_verification")`，`backend/services/onboarding_service.py:331-333`，定义 `:511-524`）；部分唯一索引 `ux_tenant_registrations_owner_email_live` 数据库兜底（`backend/models/tenant_onboarding.py:35-39,75-80`；迁移 `backend/alembic/versions/026_tenant_onboarding_auth_contract.py:193-200`）；重复归一化邮箱返回**中性 202** 且不建第二个活跃注册（端点固定 202 `backend/api/v1/auth.py:116`；中性响应体 `auth.py:146-154`：`registration_id=None` + `NEUTRAL_SIGNUP_MESSAGE`）；零售商双绑定观察不能证明 owner 双注册。
   - **但正式租户本地用户 API 可以跨租户创建同邮箱用户**【R2 新增真值】：`POST /api/v1/users`（挂载 `backend/api/app.py:130`；端点 `backend/api/v1/users.py:95-136`）运行于**租户作用域会话**（`get_tenant_db_session`），其唯一性检查 `email_exists` 仅查询**本租户 schema** 的 users 表（`backend/crud/user.py:392-411`，无跨租户查询）→ 同一规范化邮箱可经各自租户的 owner 分别创建；权限要求 `users:create`（`users.py:98`），owner 首管理员持 `ADMIN_ROLE="admin"` 且 `ADMIN_PERMISSIONS` 含 `users:create`/`roles:assign`（`backend/core/permission_registry.py:14,19,29`；owner 凭据路径 `backend/services/owner_credential_service.py:14`）；正式角色分配 `PUT /api/v1/users/{id}/roles`（`users.py:269`）。
   - 该身份登录时跨租户可见性有源码支撑：login 聚合**已验证**副本构建 `available_tenants`（`auth.py:286-292`）→ 前置门可断言该身份精确看到 W1/W2。
3. **浏览器可验证的原子性面**：【R2 恢复】**成功 fan-out（M1）可浏览器验证**——多副本由**官方 API 前置**制造（见 §4 R2 供给路径），前置门验证登录可见 W1/W2 后，忘记密码、邮件链接获取、重置、旧密码拒绝、新密码双租户接受**全部由浏览器渲染 UI 执行**（M1 = `BROWSER_WITH_OFFICIAL_API_PRECONDITION`）。
4. **必须保留为后端前置门禁的面**：部分失败回滚（M2：SCAN_INCOMPLETE / APPLY_FAILED 的 all-or-nothing，需故障注入）与自然过期（R6，1h TTL）维持 `BACKEND_PRE_GATE_ONLY`；R6 的 UI 文案等价由 R5 覆盖。

## 3. 协议阻断项（UI 缺失，不得以 API 旅程绕过）

**PB-1（零售商忘记密码发现层缺失）**：后端端点齐备（`client/auth.py:355-391`）、前端服务方法存在（`authService.ts:66`）且重置页存在（`AppRouter.tsx:93` /retailer/reset-password），但：
- 无 `/retailer/forgot-password` 路由（AppRouter 全文无此项）；
- `retailerForgotPassword` 在全部 .tsx 中**零调用**；
- `ClientLoginPage.tsx`（226 行）无任何忘记密码链接。

→ 零售商侧浏览器旅程冻结于发现层（节点 RT0，stop_on_failure=yes）。**不得设计 API 直调绕过**；【R1 明确】PB-1 为 **P1 产品阻断，移交后续 H2-C** 处置；修复后需重新冻结本协议或以增补版扩展。

## 4. Phase 3 — 供给契约（未来新运行时，仅受支持生命周期）

**允许**：官方 signup → 邮箱验证（任务 maildir 读链接，浏览器外）→ setup-credential → login；maildir 私有读取；只读 DB/API 后置校验（与旅程动作显式分离，仅作 postcondition 断言）。

**【R2 修正】M1 多副本官方供给路径（唯一授权方式）**：
1. W1/W2 owner 以**不同邮箱**各自完成官方 signup → 验证 → setup-credential → login（两个独立租户）；
2. 各自登录所属租户后，经**正式** `POST /api/v1/users` 在本租户创建**同一规范化 admin 邮箱**用户（前置供给动作，非旅程动作）；
3. 必要时经正式 `PUT /api/v1/users/{id}/roles` 分配正式角色；
4. 前置门验证：该 admin 邮箱 login 后**精确看到 W1/W2** 两个可用工作区（`auth.py:286-292`）；
5. 此后的 forgot-password、maildir 链接获取（任务私有）、reset 页、旧密码拒绝、新密码双租户接受**全部必须由浏览器渲染 UI 执行**——API 仅限上述 2/3 的官方用户供给前置，不得代替任何 forgot/reset 旅程动作。

**【R2 禁止（沿 R1 精神收窄）】**：SQL/直连 ORM/手写哈希/debug 端点制造或修复身份；以 API 代替 forgot/reset 旅程动作（例：不得用 `api.post('/auth/forgot-password')` 代替在渲染表单中输入提交）；owner 同邮箱双 signup（被源码阻止，属无效尝试）；沿用旧凭据/旧库；把 token/密码写进证据。

**身份矩阵（R1 修正后）**：A1 = persona-1@任务域（唯一 owner 注册——同邮箱二注册返回中性 202 且不建新注册）；~~A2 = 同邮箱第二租户~~（撤回：不可经官方生命周期制造）；U = 从未注册邮箱；X = 不合格邮箱（如仅存在已删除用户的邮箱——若官方生命周期无法制造，降级为 `BACKEND_PRE_GATE_ONLY` 后置断言，不做桥接）。密码：P0 供给期初值，P1 重置前值，P2 重置后值，P3 重放尝试值——全部仅存在于运行时内存与任务私有密文，不入任何证据。

## 5. Phase 5 — 未来执行契约（权威运行规则）

1. **SHA/配置冻结**：合并候选 SHA + 协议 CSV/本文档 blob 哈希写入运行 manifest；运行前 `git rev-parse` 校验无漂移，漂移即 STOP。
2. **运行时**：全新 PG16 + Redis7 容器/卷 + Alembic 037；`MPANGO_ENV=staging` 真实 JWT（无 mock auth）；`workers=1`、`retries=0`、无 grep/无 shard；后端经 production entrypoint `main:app`；前端独立回环端口经 vite 代理。
3. **视口**：desktop 1280×800、tablet 768×1024、mobile 390×844（CSV viewport 列）。
4. **前置门禁（单次权威运行前）**：健康三检查 200；F-05 家族回归核对（H2-B-R0/R1/R2 事件类在日志中可查——只读）；PB-1 状态复核（若已修复，RT0 解冻需 CTO 增补授权）。
5. **浏览器动作**：全部经渲染 UI；请求拦截仅断言形状/存在性（如"响应体不含 email 字段"），**绝不存储秘密**；maildir 令牌任务私有读取，绝不提交入证据。
6. **单次权威运行**：仅一次全量运行；产出 machine JSON、JUnit、节点 CSV 执行结果、对账表（accounting gap=0）、失败集。
7. **STOP 条件（任一即停，写报告，不得 rerun-to-green）**：
   - 受支持 UI 路由/控件缺失（含 PB-1 类新发现）；
   - 公开响应出现枚举差异（F3 vs F4 任何可观测不同）；
   - token 出现于 query/日志/存储/证据任何一处；
   - 旧密码仍可登录（R9 失败）；
   - 重放被接受（R11 失败）；
   - 部分副本更新（【R2】M1 浏览器运行中任一工作区新旧密码状态与另一侧不一致即 STOP；M2 前置门禁侧的部分副本/扫描证据同属 STOP 级缺陷上报）;
   - 出现意外的 skip/retry/conditional pass；
   - 运行时/源码 SHA 漂移。
8. **清理与证明**：停任务进程；仅删任务自有容器/卷/网络/maildir/worktree；核验端口释放；候选与保护 refs 未变证明。

## 6. Playwright 测试设计（应委托方 2026-08-23 指示承接 OpenCode 部分而补充；**仅设计，未实现为可执行运行、未运行、未改产品代码**）

### 6.1 目标文件布局（未来实现时的建议结构，本次不创建）

```
frontend/e2e/forgot-reset/
  forgot-reset.spec.ts        # 权威旅程：按节点 CSV 顺序的单一 full-run describe
  nodes/                      # 每节点一个步骤函数（与 CSV node_id 一一对应）
  helpers/maildir.ts          # 任务私有 maildir 读取（仅返回内存中的链接，禁止落盘）
  helpers/neutral.ts          # 中性比对：捕获 F3/F4 响应做逐字节等价断言
  helpers/storage-sweep.ts    # R12/R13：localStorage/sessionStorage/console/网络面扫描
  fixtures/identities.ts      # 从运行时环境变量注入身份（绝不硬编码于仓库）
```

### 6.2 关键设计约束（映射 CSV）

1. **单次权威运行**：一个 `test.describe.serial`；`retries=0`、`workers=1`（playwright.config 片段设计：`fullyParallel:false, workers:1, retries:0`）；节点失败即整趟 STOP 并输出失败集，不得选择性重跑。
2. **中性等价断言**（F3/F4）：经 `page.route` 拦截仅记录 `status + 响应体哈希 + 响应体长度`（不存原文，防秘密入证据）；断言两组 (status, bodyHash) 相等且页面可见文案 `toBeVisible()` 文本一致。锚点 `ForgotPasswordPage.tsx:14`（常量文案）+ `auth.py:829-833`。
3. **fragment-only 传输**（R1/R2）：`page.goto(linkFromMaildir)` 后断言 `page.url()` 匹配 `/reset-password$`（无 `#`）；`window.location.hash === ''`；`history.length` 合法。锚点 `ResetPasswordPage.tsx:41-49`。
4. **query 拒绝**（R3）：`page.goto('/reset-password?resetToken=x')` 断言 Invalid Link 面板可见且 URL 已被清洗为 pathname。锚点 `ResetPasswordPage.tsx:35-39,76-97`。
5. **存储卫生**（R12）：旅程结束后在页面上下文执行枚举脚本，断言两 storage 的 key/value 均不匹配 `/resetToken|password|Authorization/i`；console 消息与网络日志同样过滤断言。**断言失败信息只输出命中字段的 key 名，绝不输出值**。
6. **重放与一次性**（R11）：同令牌二次提交断言 401 + 中性文案，随后以 P2 再次登录成功（复验 P3 未生效）。
7. **多副本**（M1）：【R2 恢复浏览器设计】前置：官方 API 供给同邮箱双租户 admin（§4 R2 路径步骤 1-4，含登录精确见 W1/W2 的前置门断言）；浏览器侧：该 admin 在 W1 工作区经渲染 UI 走 forgot → maildir 取链（任务私有）→ reset 成功 → 断言**两个**工作区（双 `browserContext`，storageState 独立）新密码 P2 均可登录、旧密码 P1 均被拒。
8. **maildir helper**：仅 `fs.readFile` 任务运行时目录 → 正则提取链接 → 返回字符串；**禁止** `console.log`/截图/trace 含链接；trace 设 `screenshots:'off'` 或对地址栏区域做截断处理（设计取舍：优先关闭 trace 截图，仅保留 DOM 快照无 URL）。
9. **视图口**：三个 `test.describe` 内以 `page.setViewportSize` 逐节点切换（CSV viewport 列为唯一事实源）。
10. **证据输出**：machine JSON（每节点 result/elapsed/断言摘要）、JUnit XML、节点 CSV 执行回填、对账表（29 节点全部 accounted，gap=0）。

### 6.3 明确不做

不实现/不运行上述代码；不创建 `frontend/e2e/`；不修改 playwright 配置；不新增依赖。下一步动作等待 CTO 同时接受：① OpenCode WSL literal zero-red 结果；② 本协议（经 B0→R1→R2 修正链的当前版本）。

## 7. 节点清单与统计（R2 恢复重算）

- **总节点数：29**（行集不变；`2026-08-23_..._node_inventory.csv`）
- 【R2】浏览器节点 **24** = 23 个纯 `BROWSER`/`BROWSER+POSTCOND` 单副本节点 + **M1**（`BROWSER_WITH_OFFICIAL_API_PRECONDITION`）；非浏览器节点 **5**（F6 maildir 前置、R6 过期=前置门禁、M2 原子性=前置门禁、R13 证据后置、RT0 协议阻断行）
- **browser / backend-pre-gate 分割（R2 后）**：浏览器覆盖单副本全链路 + 中性/传输/卫生面 + 多副本**成功** fan-out（M1，官方 API 前置供给）；失败原子性（M2）与自然过期（R6）维持 `BACKEND_PRE_GATE_ONLY`。

## 8. 已知阻断/假设/风险（R2 修正后）

- **PB-1**（§3）：零售商发现层缺失 → 零售商旅程冻结，**P1 产品阻断移交 H2-C**。
- **多副本供给假设（R2 确立）**：owner signup 唯一性保留（R1）；多副本唯一官方路径 = 各租户 owner 经正式 `POST /api/v1/users` 创建同邮箱用户（§2.5-2/§4 锚点）。若未来源变更（如 `email_exists` 改为跨租户），M1 前置失效 → STOP 并报告，不做桥接。
- **风险**：F5 的"不合格邮箱"若无法经官方生命周期制造（如无法产生仅含已删除用户的邮箱），按 §4 降级为后置断言；maildir 链接的 trace/截图泄漏风险已以 6.2-8 设计对冲。
- **资格声明**：本任务（B0/R1/R2）零运行时、零源码修改、零测试修改；GitNexus 未索引（约束性跳过）；OpenCode 并行任务资产零接触。

## 8a. 未来浏览器范围（R2 澄清）

- **批发商受支持 UI 旅程**：在运行时验收（§5 前置门禁）通过后可执行——即 CSV 24 个浏览器节点（含 M1）。
- **零售商旅程**：冻结直至 H2-C 交付 PB-1 修复；届时需增补/重新冻结协议。
- **多副本原子性**：成功 fan-out 由浏览器经官方 API 前置供给后验证（M1）；失败路径原子性（M2）由后端前置门禁证明——**任何路径都不得**以 SQL/直接 ORM/手写哈希/debug 端点伪造副本或修复数据。

## 9. 交付元数据

- 修改文件（本分支相对 `218be690` 的完整 delta，恰好 3 个）：
  1. `docs/ai-reports/test-plans/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_browser_protocol.md`（本文件）
  2. `docs/ai-reports/test-plans/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_node_inventory.csv`
  3. `ai-ledger/product-ai/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_browser_protocol_freeze.md`
- 完整 commit SHA：见 §10（发布后回填记录于台账文件；本文件在发布时以 commit 自身哈希为准，故此处不预写）。
- 锚点审阅范围：§2.1-2.4 全表（前端 6 文件 + 后端 5 文件）。

## 10. 发布记录（push 后由台账承载，此处留白以保持三文件 delta 精确）

本文件为冻结版本；发布与验证证明见台账文件。
