# DC-12R1-MVP-L1-J1-H2-C-R0 — 零售商恢复发现与门户返回合同冻结

- 日期：2026-08-26（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R0（Retailer Password-Recovery Discovery
  and Portal-Return Contract Freeze）
- 验证层级：V1_SOURCE；CLAIM_CEILING：`CONTRACT_AND_IMPACT_ANALYSIS_ONLY`
- BASE：`origin/product-dev-recovered@2c20d58c88a0a8f5175f4d11041d03b6ca785e06`
  （fetch/prune 后本地 == 远端复核一致）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r0-retailer-recovery-discovery-contract-2026-08-26`
- 变更类别：仅新增 3 个文档文件；零产品源码/测试/迁移/依赖/配置/部署变更；
  未运行产品运行时、Playwright、PG 或 Redis。

## 1. 交付物（恰 3 文件）

1. `docs/test-plans/2026-08-26_dc12r1_mvp_l1_j1_h2_c_retailer_recovery_discovery_contract.md`
   —— 合同冻结主文件（源码真值、RT0/新缺陷区分、影响分析、12 点合同、
   R1 允许清单、禁止事项）。
2. `docs/test-plans/2026-08-26_dc12r1_mvp_l1_j1_h2_c_node_inventory.csv`
   —— HC01-HC16 节点清单（15 列，与 j1h2b harness inventory 同构；
   覆盖入口发现、无效门户零调用、表单校验、四类中性响应、双击单 POST、
   邮件 fragment、URL 清理与泄漏扫描、成功返回正确门户、legacy 链接、
   伪造 token、390px 响应式×2）。
3. 本台账。

## 2. 源码真值验证（Phase 1，全部复核通过）

任务给定的 7 项源码真值全部在 BASE 树中逐项验证（file:line 见合同
§1）：后端端点与前端 service 已存在；`/retailer/forgot-password` 路由与
页面缺失；`ClientLoginPage` 无入口；reset 链接仅含 `resetToken`；重置
成功 CTA 指向批发商 `/login`。

补充真值：`ClientLoginPage` 的 `w` 规范化/无效门户模式（复用依据）、
`build_retailer_setup_link` 的 fragment `&w=` 先例、
`request_password_reset` 的中性化设计与既有 `wholesaler_code` 参数。

## 3. RT0 与新缺陷区分（关键裁定）

- RT0（不变）：零售商发现层缺失 = UI 发现缺口（真值 4+5）；
  禁止 API 绕过。H2-C-R1 完成后解除。
- 新发现关联缺陷（真值 6+7 + legacy 歧义）：reset 链接无供应商代码、
  成功 CTA 错指批发商登录、legacy 链接无中性引导。
- 后端链路**已存在且中性**（forgot → request_password_reset →
  fragment-only 链接 → reset 端点）；台账与合同均不得将其写成缺失。
  R1 后端改动仅限链接构建器追加公共 `w`。

## 4. 影响分析（GitNexus @ 2c20d58c = 28,852 nodes / 60,243 edges + grep 复核）

五个符号的上游影响闭合于：AppRouter（1 条新公共路由 + P25 路由清单
测试同步）、ClientLoginPage（入口 + 4 个测试文件断言）、
RetailerResetPasswordPage（fragment w + 成功跳转 + 2 个测试文件）、
build_retailer_reset_link（签名 + 单一调用点）、
request_password_reset（邮件负载 + 3 个后端测试断言）。
`authService.ts` 无需变更（影响分析未发现必要性）。

## 5. 质量门结果

- 三文件精确范围：`git status`/`git diff --name-only` 仅 3 个授权文件。
- CSV 严格解析：16 数据行 × 15 列，`csv` 模块 strict 解析通过；
  `node_id` 唯一（HC01-HC16 无重复）；全字段非空（无空 oracle）。
- `git diff --check`：干净。
- scoped pre-commit（3 文件，含 detect-secrets，`.secrets.baseline`）：
  全部 Passed。
- 三文件严格 UTF-8、无 BOM。
- GitNexus：BASE 重建索引（28,852 nodes / 60,243 edges / 838 clusters），
  `status` 于本分支提交 up-to-date。
- 未修改冻结 j1h2b-forgot-reset harness（`git diff` 该目录为空）。
- 产品运行时/Playwright/PG/Redis：零执行。

## 6. R0-R1 精化（Contract Determinism and Legacy Compatibility Closure）

R0 verdict（§6 原裁决）**被 R0-R1 精确合同取代**。R0-R1 于同一组三文件内
完成以下修正（BASE `e8858dd6`，分支
`zcode/dc12r1-mvp-l1-j1-h2-c-r0-r1-contract-truth-closure-2026-08-26`）：

1. **canonical neutrality 冻结**：精确键集 `success/data/message/timestamp`；
   `success=true`、`data={}`、`message` 为固定中性常量；`timestamp`
   必须存在且可解析；比较时仅将 timestamp 值替换为 sentinel 后逐键相等；
   不做 raw-byte 或时序相等声明；timing sidechannel 明确
   OUT_OF_SCOPE。（HC07-HC10 同步改为 canonical response equality。）
2. **HC12 精化**：resetToken 永不进入 query/storage/日志/console/network
   metadata；`w` 为公共代码，仅允许出现在初始 fragment 与成功后
   canonical `/retail/login?w=` URL；`w` 不进入 reset POST body、
   storage 或日志。
3. **legacy 兼容**：legacy 链接携带有效 token 仍允许完成密码重置；
   成功后仅显示 "Return to the portal link your supplier provided"，
   不提供 `/login` 链接、不猜测门户（HC14 同步改写）。
4. **HC02 精化**：无效门户判例改为缺失 `w` 与明确畸形 `w=BAD%21`。
5. **DB canonical w**：reset 邮件中的 `w` 必须来自数据库匹配到的
   canonical wholesaler code（`lower(w.code)=lower(:code)` 匹配后取
   `w.code`）；追加节点 HC17（小写调用输入 → DB canonical 大写代码）。
   HC01-HC16 ID 与顺序保持稳定，HC17 仅追加。
6. **影响分析修正**：删除无证据的 P25 描述（经核实 P25_RouteInventory
   只钉住 PlatformRoute 下 19 条平台路由，公共路由不在其清单内）；
   补充真实受影响测试范围，含
   `test_dc12r1_j1_h2b_forgot_password_runtime_closure.py`。

R0-R1 质量门：delta 恰三个 R0 文档文件；CSV 17 数据行 × 15 列、
ID 唯一（HC01-HC17）、oracle 全非空；`git diff --check` 干净；
scoped pre-commit + detect-secrets Passed；三文件严格 UTF-8 无 BOM；
未实施 H2-C-R1。

## 7. 裁决

ORIGINAL_R0_VERDICT: **PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R0_CONTRACT_REVIEW**
（已被 R0-R1 精确合同取代）

FINAL VERDICT: **PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R0_R1_CONTRACT_TRUTH_CLOSURE**

CLAIM_CEILING：`CONTRACT_AND_IMPACT_ANALYSIS_ONLY`。
完成后 STOP：等待 CTO 审阅合同与节点清单，再授权 H2-C-R1 实现；
未启动 PRICING、SKU、部署或其他产品工作。
