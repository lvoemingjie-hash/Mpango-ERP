# DC-12R1-MVP-L1-J1-H2-C-R0 — Retailer Password-Recovery Discovery and Portal-Return Contract Freeze

- 日期：2026-08-26（+08:00）；执行者：Zcode
- 验证层级：V1_SOURCE；CLAIM_CEILING：`CONTRACT_AND_IMPACT_ANALYSIS_ONLY`
- BASE：`origin/product-dev-recovered@2c20d58c88a0a8f5175f4d11041d03b6ca785e06`（本地 == 远端复核）
- 本文件为合同冻结与影响分析，不修改产品源码，不运行产品运行时。

## 1. 已验证的源码真值（file:line 于 BASE 2c20d58c）

| # | 真值 | 锚点 |
|---|---|---|
| 1 | `POST /client/auth/forgot-password` 已存在（零售商公共忘记密码端点） | `backend/api/v1/client/auth.py:356` |
| 2 | `authService.retailerForgotPassword` 已存在，空 `Authorization` 头 + `skipAuthInterceptors: true` | `frontend/src/services/authService.ts:77-84` |
| 3 | `/retailer/reset-password` 路由与 `RetailerResetPasswordPage` 已存在 | `frontend/src/router/AppRouter.tsx:93`；`frontend/src/pages/retailer/RetailerResetPasswordPage.tsx` |
| 4 | 缺少 `/retailer/forgot-password` 路由与页面（仅批发商 `/forgot-password`，AppRouter.tsx:87） | `frontend/src/router/AppRouter.tsx` 全文无零售商 forgot 路由 |
| 5 | `ClientLoginPage` 无任何忘记密码入口 | `frontend/src/pages/client/ClientLoginPage.tsx`（grep forgot/reset = 0 命中） |
| 6 | `build_retailer_reset_link` 仅含 `resetToken`，不携带供应商代码 | `backend/services/onboarding_service.py:489-497` |
| 7 | 重置成功 CTA 当前指向批发商 `/login` | `frontend/src/pages/retailer/RetailerResetPasswordPage.tsx:71-73` |

补充真值（分析中发现，供 R1 参考）：

- `ClientLoginPage` 已实现 `w` 参数规范化（`trim().toUpperCase()`）与
  `WHOLESALER_CODE_RE` 有效性检查；无效 `w` 显示中性无效门户文案且零 API
  调用（`ClientLoginPage.tsx:31-36,55-59`）。H2-C 忘记密码页必须复用同一
  规范化与无效门户语义。
- `build_retailer_setup_link` 已有 fragment 追加 `&w=<quote(code)>` 的先例
  （`onboarding_service.py:478-481`）；reset 链接的 `w` 追加应沿用同一模式。
- `RetailerProvisioningService.request_password_reset` 已按设计中性化：
  无账户 / 邮箱未验证 / 错误供应商代码 / SMTP 失败对调用方完全同形，
  SMTP 失败回滚 token（`retailer_provisioning_service.py:896-950`）。
  该服务已接收 `wholesaler_code` 参数，向链接构建器传递公共代码无需
  schema 变更。

## 2. RT0 阻断与新发现关联缺陷的区分

### 2.1 原始 RT0 阻断（保持不变，H2-C-R1 解除）

RT0 = `BLOCKED_BY_H2_C`（j1h2b-forgot-reset README PB-1）：
**零售商发现层缺失** —— 零售商没有任何可发现的忘记密码入口
（真值 4 + 真值 5）。RT0 的性质是 UI 发现层缺口，且
**禁止以 API 绕过缺失的零售商 UI**。

### 2.2 新发现的关联缺陷（H2-C-R1 一并修复，非后端缺失）

1. **门户回传缺口（真值 6）**：reset 邮件链接不携带供应商代码，
   重置完成后无法确定应返回哪个供应商门户。
2. **错误返回目标（真值 7）**：重置成功 CTA 指向批发商 `/login`，
   将零售商错误导向批发商登录页。
3. **legacy 链接歧义**：不带 `w` 的历史 reset 链接无法（也不得）猜测
   供应商；需要中性引导状态而非批发商登录跳转。

### 2.3 后端链路状态（如实记载，不得写成缺失）

后端忘记/重置链路**已存在且中性**：`POST /client/auth/forgot-password`
（client/auth.py:356）→ `request_password_reset`（中性、token 回滚）
→ `build_retailer_reset_link`（onboarding_service.py:489，fragment-only
token）→ `POST /client/auth/reset-password`。H2-C-R0/R1 不需要新增任何
后端端点；R1 的后端改动仅限 reset 邮件链接追加公共 `w` 代码。

## 3. 上游影响分析（GitNexus 索引 @ 2c20d58c：28,852 nodes / 60,243 edges；grep 复核）

| 符号 | 上游引用 | 影响判定 |
|---|---|---|
| `ClientLoginPage` | `AppRouter.tsx`（渲染）；测试 `Dc12r1S2RetailerPortal`、`DualEntrySelfJoin`、`InviteAuthoringClosure`、`Pw1R4B4RetailerPermissionContext` | 新增忘记密码入口链接影响登录页 UI 与 4 个测试文件的既有断言；R1 需更新受影响断言 |
| `AppRouter` | `App.tsx`（挂载）；平台导航测试（P25 route inventory 等）与认证测试 | 新增 1 条公共路由 `/retailer/forgot-password`；P25 路由清单类测试可能需要同步；不影响已认证导航断言 |
| `RetailerResetPasswordPage` | `AppRouter.tsx`；测试 `RetailerCredentialPages`、`PublicPasswordRecoveryInterceptor` | 读取 fragment `w` + 成功跳转改为 `/retail/login?w=` 影响 2 个测试文件；`CredentialLifecyclePages` 不引用该页（grep 0 命中），不受影响 |
| `build_retailer_reset_link` | 仅 `retailer_provisioning_service.py:942` 单一调用点（定义于 onboarding_service.py:489） | 追加 `w` 参数影响签名与单一调用点；无其他调用方 |
| `RetailerProvisioningService.request_password_reset` | `backend/api/v1/client/auth.py`（路由）；后端测试 `test_dc12r1_s1_r1_corrections`、`test_dc12r1_s1_r2_strict_mapping`、`test_dc12r1_s1_retailer_identity` | 服务合同（中性）不变；仅邮件负载内链接变化；3 个测试文件的链接断言需同步 |

结论：R1 影响面闭合于前端路由/两页/登录页 + 后端链接构建器与既有断言；
`authService.ts` 无需变更（`retailerForgotPassword` 已满足合同 4），
除非影响分析证明必要。

## 4. 冻结的产品合同（12 点，R1 实现与验收的权威依据）

1. **canonical discovery route**：
   `/retailer/forgot-password?w=<NORMALIZED_CODE>`。
   `w` 的规范化与有效性判定复用 `ClientLoginPage` 既有语义
   （trim + UPPERCASE + `WHOLESALER_CODE_RE`）。
2. **入口可见性**：只有 `w` 有效的 `/retail/login?w=<CODE>` 页面显示
   忘记密码入口。
3. **无效门户零调用**：`w` 缺失或畸形时显示中性无效门户状态
   （复用登录页无效门户文案语义），**零 recovery POST**。
4. **表单与调用**：忘记密码页要求 email，提交调用既有
   `authService.retailerForgotPassword`（`/client/auth/forgot-password`）；
   不新增端点。
5. **中性结果**：有账户、无账户、错误供应商、未验证账户必须显示
   **完全相同**的中性结果（服务端已保证同形；前端不得添加可区分状态）。
6. **reset 邮件链接形态**：
   `/retailer/reset-password#resetToken=<SECRET>&w=<PUBLIC_CODE>`
   （`w` 为规范化公共代码，沿 `build_retailer_setup_link` 的
   `quote(code, safe='')` 先例）。
7. **fragment-only**：`resetToken` 只能位于 URL fragment；不得进入
   query string、服务器日志或浏览器 storage。
8. **reset 页 w 处理**：reset 页在清理 URL（移除 fragment）前读取并
   验证公共 `w`，仅保存在内存（组件状态），不写入任何 storage。
9. **成功返回**：重置成功后进入 `/retail/login?w=<CODE>`（该供应商
   门户登录页）；**不得**进入批发商 `/login`。
10. **legacy 链接**：缺少 `w` 的 reset 链接不得猜测供应商、不得跳转
    批发商登录；显示中性引导："返回供应商提供的门户链接"
    （Return to the portal link your supplier provided.）。
11. **无枚举、无绕过**：无多轮供应商选择器、无公共租户枚举、
    无 API 绕过（RT0 纪律延续到 R1）。
12. **390px 响应式**：忘记密码页与重置页在 390px 模拟视口下
    无横向溢出。

## 5. 节点清单

见同目录
`2026-08-26_dc12r1_mvp_l1_j1_h2_c_node_inventory.csv`
（HC01-HC16，15 列，与 j1h2b harness inventory 同构）。

## 6. R1 实现允许清单（提出，未执行）

- `frontend/src/router/AppRouter.tsx`（新增公共路由）
- `frontend/src/pages/client/ClientLoginPage.tsx`（忘记密码入口，仅有效门户）
- `frontend/src/pages/retailer/RetailerForgotPasswordPage.tsx`（新增）
- `frontend/src/pages/retailer/RetailerResetPasswordPage.tsx`（fragment `w` + 成功返回）
- `backend/services/onboarding_service.py`（reset 链接追加 `w`）
- `backend/services/retailer_provisioning_service.py`（调用点传递公共代码）
- 对应前后端测试文件（`RetailerCredentialPages`、`PublicPasswordRecoveryInterceptor`、S1 后端测试断言等）

除非影响分析证明必要，`frontend/src/services/authService.ts` 保持不变
（当前分析未发现必要性）。

## 7. 禁止事项（R0 与 R1 均适用）

- migration / model / schema / dependency / lockfile 修改。
- 修改已冻结的 `j1h2b-forgot-reset` harness。
- SQL / ORM / debug endpoint 桥接。
- 产品运行时、Playwright、合并、部署（R0 阶段）。
- 启动 PRICING、SKU 或 H2-C-R1 实现（等待 CTO 授权）。

## 8. 裁决

FINAL VERDICT: **PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R0_CONTRACT_REVIEW**

CLAIM_CEILING：`CONTRACT_AND_IMPACT_ANALYSIS_ONLY`。
等待 CTO 审阅本合同与节点清单后再授权 H2-C-R1 实现。
