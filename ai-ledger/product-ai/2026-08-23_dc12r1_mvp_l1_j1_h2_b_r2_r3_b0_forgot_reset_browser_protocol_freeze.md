# AI Ledger — DC-12R1-MVP-L1-J1-H2-B-R2-R3-B0 Forgot/Reset 浏览器协议冻结

> **R3 修正版（2026-08-24）**：父提交 R2=`cfd2446`；分支 `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-b0-r3-final-protocol-truth-2026-08-24`。裁决目标更新为 `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R3_B0_R3_PROTOCOL_FINAL_REVIEW`。B0/R1/R2 历史全部保留（R2 记录见下）。
>
> **R3 核心变更**：
> 1. **共享身份 M 定义收口**：W1/W2 owner 仍用不同邮箱；M 用同一规范化邮箱；**两次 `POST /api/v1/users` 必须使用同一初始密码 P1**；**两侧均正式分配 admin role**；前置门验证 M 登录**精确**得到 W1/W2（多/少/含其他租户即失败）。CSV M1 行同步（同邮箱 + 同 P1 + 双侧 admin role，缺一即前置门失败）。
> 2. **源码锚点按精确行号修正**：`permission_registry.py:9`（ADMIN_ROLE）、`:17-28`（ADMIN_PERMISSIONS 块）、`users:create`=:19、`roles:assign`=:28；`owner_credential_service.py:14,30,186-190`（owner→admin RBAC 创建切片）。
> 3. **下一门禁改为顺序链**：R2-R4 helper 修复冻结 → Kilo bounded review → OpenCode 双 fresh-stack literal zero-red PASS → 才允许实现/运行本浏览器协议。既有 OpenCode STOP 仅作为**历史失败证据**，不是待 CTO 接受的 zero-red 结果。
> 4. 统计保持 **24 browser + 5 non-browser = 29**（不变）。

> **R2 修正版（2026-08-24）**【历史保留】：父提交 R1=`48473ed`；分支 `...b0-r2-official-user-provisioning-truth-2026-08-24`；裁决目标 `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R3_B0_R2_PROTOCOL_TRUTH_REVIEW`。
>
> **R2 核心变更**：
> 1. **结论收窄（不撤回 R1 owner signup 唯一性）**：owner signup 不能产生双活跃注册（保留）；**但正式租户本地 `POST /api/v1/users` 可跨两租户创建同邮箱用户**——`email_exists` 仅查本租户 schema（`backend/crud/user.py:392-411`）、端点运行于租户作用域会话（`backend/api/v1/users.py:95-136`，挂载 `api/app.py:130`）、权限 `users:create` 属 admin 集、正式角色分配 `PUT /api/v1/users/{id}/roles`（`users.py:269`）、登录跨租户可见 `available_tenants`（`auth.py:286-292`）。
> 2. **M1 恢复 `BROWSER_WITH_OFFICIAL_API_PRECONDITION`**：官方 API 仅限供给前置；forgot/邮件链接/重置/旧密码拒绝/新密码双租户接受全部浏览器 UI。
> 3. M2 与 R6 维持 `BACKEND_PRE_GATE_ONLY`；禁止 SQL/直接 ORM/手写哈希/debug 端点；禁止 API 代替 forgot/reset 旅程动作。
> 4. 统计恢复：**24 browser（23 纯 BROWSER/BROWSER+POSTCOND + M1）+ 5 non-browser（F6/R6/M2/R13/RT0）= 29**（csv.DictReader 严格解析复核）。
> 5. signup 中性响应锚点补充 `auth.py:146-154`（registration_id=None + NEUTRAL_SIGNUP_MESSAGE）。

- 日期：2026-08-23（B0）；R1/R2/R3 修正 2026-08-24（+08:00）
- 执行者：ZCode（B0 承接 OpenCode 文档与测试设计；R1/R2/R3 证据真值修正。全程零运行/零产品修改）
- 分支（当前，R3）：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-b0-r3-final-protocol-truth-2026-08-24`（修正链：B0 `...b0-forgot-reset-browser-protocol-2026-08-23` → R1 `...b0-r1-provisioning-truth-2026-08-23` → R2 `...b0-r2-official-user-provisioning-truth-2026-08-24` → R3）
- 冻结源：`218be690a6d5ad3551c31fa28087964440c888c9`（== 远端源分支 HEAD，核验通过）
- 保护基线：`product-dev-recovered` == `6e9470a1daa5d6eece29724316fdd8aef6b737c1`（核验通过，未触碰）
- Kilo 审批：`b7e67e242fe3e7bdd663e8c5aead2f599c25baa8`（核验通过）

## 裁决请求（当前版本，R3 统一）

`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R3_B0_R3_PROTOCOL_FINAL_REVIEW`

## 交付摘要

| 项 | 值 |
|---|---|
| 修改文件数 | 恰好 3（协议 md / 节点 CSV / 本台账） |
| 节点总数 | 【R3 保持】29 = browser 24（23 纯单副本 + M1 官方API前置浏览器节点，M=同邮箱+同P1+双侧admin role）+ non-browser 5（F6/R6/M2/R13/RT0） |
| 协议阻断 | PB-1：零售商忘记密码发现层缺失（authService.ts:66 零调用；无 /retailer/forgot-password 路由；ClientLoginPage 无链接）。P1 产品阻断，移交 H2-C，禁止 API 绕过（R1 裁定保留） |
| browser/pre-gate 分割 | 【R2】M1=BROWSER_WITH_OFFICIAL_API_PRECONDITION（成功 fan-out 浏览器可验证）；M2 失败原子性与 R6 自然过期维持 BACKEND_PRE_GATE_ONLY |
| GitNexus | 未索引（NOT_INDEXED_BY_CONSTRAINT，不执行 analyze 以免工件污染冻结 worktree） |
| 运行时/源码/测试 | 零启动、零修改、零 Playwright 实现 |

## R1 供给真值修正记录（2026-08-24，基线 8b0671c）【历史保留】

- **撤回**：B0 曾主张"官方 signup 允许同一 owner email 创建两个活跃批发商注册"——错误（R2 未撤回本结论）。
- **源码真值**（冻结源 218be690 就地核验）：
  - `_live_registration_for_email` 阻止第二个活跃注册（`backend/services/onboarding_service.py:331-333`，定义 `:511-524`）；
  - 部分唯一索引 `ux_tenant_registrations_owner_email_live` 强制唯一（`backend/models/tenant_onboarding.py:35-39,75-80`；迁移 `backend/alembic/versions/026_tenant_onboarding_auth_contract.py:193-200`）；
  - 重复归一化邮箱 signup 返回中性 202 且不建第二个活跃注册（`backend/api/v1/auth.py:116`；【R2 补】中性响应体 `auth.py:146-154`）；
  - 既往浏览器观察中的零售商双绑定现象不能证明批发商 owner 双注册。
- 【R2 备注】R1 当时将 M1 移类 PRE_GATE_ONLY 并按 23/6 重算——该处置在 R2 依"正式用户 API 可跨租户建同邮箱"真值恢复（见顶部 R2 变更 1/2/4）。
- **附带数据修正（如实记录）**：B0 CSV 存在 3 行列数缺陷（R7-POLICY/R7-POLICY-M 缺 phase 列、M2 缺 expected_http 列），R1 补正并在行内 notes 标注 `[R1]...已补正`；修正后统计以 csv.DictReader 严格解析为准。

## 质量门执行记录（R3 发布时）

- [x] 三文件精确 delta（相对父提交 cfd2446，仅原三文件）
- [x] `git diff --check`（无 whitespace 错误）
- [x] 严格 CSV 解析（29 行 × 15 列，无畸形行；统计 24/5 复核）
- [x] 严格 UTF-8 / 无 BOM / 无 mojibake
- [x] 范围化密钥扫描（无实值；仅契约描述性文本）
- [x] local == remote（push 后 rev-parse 双侧一致）
- [x] 候选 refs 与保护 refs 未变（product-dev-recovered 仍为 6e9470a1）

## 发布证明

R3 发布 commit 即本台账所在提交；SHA 于 push 输出与 remote refs 可验（local==remote 断言即证明）。

## 下一步门禁（R3 顺序链）

**R2-R4 helper 修复冻结 → Kilo bounded review → OpenCode 双 fresh-stack literal zero-red PASS → 才允许实现/运行本浏览器协议。**

- 既有 OpenCode STOP 仅作为历史失败证据存档，不构成、也不得写成"待 CTO 接受的 zero-red 结果"。
- 链条全部满足前：不实现 Playwright、不启动运行时、不实施 H2-C。
