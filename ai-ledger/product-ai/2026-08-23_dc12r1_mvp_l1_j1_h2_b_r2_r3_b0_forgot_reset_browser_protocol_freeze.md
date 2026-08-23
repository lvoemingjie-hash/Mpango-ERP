# AI Ledger — DC-12R1-MVP-L1-J1-H2-B-R2-R3-B0 Forgot/Reset 浏览器协议冻结

> **R1 修正版（2026-08-24）**：本台账承载 B0 历史证据 + R1 供给真值修正（分支 `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-b0-r1-provisioning-truth-2026-08-23`，基线 `8b0671c`）。裁决目标更新为 `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R3_B0_R1_PROTOCOL_TRUTH_REVIEW`。B0 原裁决请求保留于下。

- 日期：2026-08-23（B0）；R1 修正 2026-08-24（+08:00）
- 执行者：ZCode（应委托方指示承接 OpenCode 配额受限部分的文档与 Playwright 测试设计；仍零运行/零产品修改）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r3-b0-forgot-reset-browser-protocol-2026-08-23`
- 冻结源：`218be690a6d5ad3551c31fa28087964440c888c9`（== 远端源分支 HEAD，核验通过）
- 保护基线：`product-dev-recovered` == `6e9470a1daa5d6eece29724316fdd8aef6b737c1`（核验通过，未触碰）
- Kilo 审批：`b7e67e242fe3e7bdd663e8c5aead2f599c25baa8`（核验通过）

## 裁决请求

`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R3_B0_BROWSER_PROTOCOL_FREEZE_REVIEW`

## 交付摘要

| 项 | 值 |
|---|---|
| 修改文件数 | 恰好 3（协议 md / 节点 CSV / 本台账） |
| 节点总数 | 【R1 重算】29（浏览器权威 **23** + 前置/后置/阻断 **6**；行集不变，M1 移类） |
| 协议阻断 | PB-1：零售商忘记密码发现层缺失（authService.ts:66 零调用；无 /retailer/forgot-password 路由；ClientLoginPage 无链接）。【R1】P1 产品阻断，移交 H2-C，禁止 API 绕过 |
| browser/pre-gate 分割 | 【R1 修正】M1 成功 fan-out 与 M2 失败原子性、R6 自然过期**全部**属 BACKEND_PRE_GATE_ONLY；多副本不可经受支持生命周期制造，浏览器旅程不得以 SQL/API 桥接伪造副本 |
| GitNexus | 未索引（NOT_INDEXED_BY_CONSTRAINT，不执行 analyze 以免工件污染冻结 worktree） |
| 运行时/源码/测试 | 零启动、零修改 |

## R1 供给真值修正记录（2026-08-24，基线 8b0671c）

- **撤回**：B0 曾主张"官方 signup 允许同一 owner email 创建两个活跃批发商注册"——错误。
- **源码真值**（冻结源 218be690 就地核验）：
  - `_live_registration_for_email` 阻止第二个活跃注册（`backend/services/onboarding_service.py:331-333`，定义 `:511-524`）；
  - 部分唯一索引 `ux_tenant_registrations_owner_email_live` 强制唯一（`backend/models/tenant_onboarding.py:35-39,75-80`；迁移 `backend/alembic/versions/026_tenant_onboarding_auth_contract.py:193-200`）；
  - 重复归一化邮箱 signup 返回中性 202 且不建第二个活跃注册（`backend/api/v1/auth.py:116` + onboarding_service 上述分支）；
  - 既往浏览器观察中的零售商双绑定现象不能证明批发商 owner 双注册。
- **重分类**：M1 → PRE_GATE_ONLY（CSV 行已改），统计重算 23/6/29；M1/M2 的浏览器供给设计与 STOP 措辞同步修正。
- **附带数据修正（如实记录）**：B0 CSV 存在 3 行列数缺陷（R7-POLICY/R7-POLICY-M 缺 phase 列、M2 缺 expected_http 列），R1 补正并在行内 notes 标注 `[R1]...已补正`；该缺陷曾使 B0 的 24/5 统计建立在解析歧义上，修正后统计以 csv.DictReader 严格解析为准。
- **范围澄清**：批发商受支持 UI 旅程可于运行时验收后执行；零售商旅程冻结至 H2-C；多副本原子性由后端前置门禁证明。

## 质量门执行记录（发布时）

- [x] 三文件精确 delta（git diff --name-only 218be690..HEAD）
- [x] `git diff --check`（无 whitespace 错误）
- [x] 严格 UTF-8 / 无 BOM / 无 mojibake
- [x] 范围化密钥扫描（token/password/Authorization 模式仅出现于契约描述性文本，无实值）
- [x] local == remote（push 后 rev-parse 双侧一致）
- [x] 候选 refs 与保护 refs 未变（product-dev-recovered 仍为 6e9470a1）

## 发布证明（push 后回填）

- commit SHA：（见下方"发布回填"）
- 回填：由发布提交自身承载——push 的 commit 即为本台账所记录的发布物，其 SHA 在 push 输出与 remote refs 中可验（local==remote 断言即证明）。

## 下一步门禁

等待 CTO 同时接受：
1. OpenCode WSL literal zero-red 结果（其配额恢复后完成）；
2. 本冻结浏览器协议。

在两者均被接受前，不开始可执行 Playwright 实现，不启动运行时。
