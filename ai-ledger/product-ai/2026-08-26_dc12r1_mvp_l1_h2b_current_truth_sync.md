# DC-12R1-MVP-L1-CT1 — H2-B Current-Truth 与预交付队列同步

- 日期：2026-08-26（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-CT1（H2-B Current-Truth and Pre-Delivery Queue
  Synchronization）
- 变更类别：`DOCS_ONLY_CURRENT_TRUTH`；验证层级 `V1_SOURCE`
- 基线（BASE）：`origin/product-dev-recovered@436d61e2dfed88a9469e4572615b98b9c4a7aed4`
  （H2-B 受控合并，MERGED_AND_BROWSER_VERIFIED；远端复核一致）
- 规划源（PLANNING_SOURCE）：`addda5b688319a0f5e457af971a2ae7afcae8276`
  （"docs: add MVP pricing and reorder execution queue"，分支
  `codex/dc12r1-mvp-l1-pricing-reorder-execution-queue-2026-08-26`，
  父提交为合并前 TARGET `6e9470a1`；非当前基线祖先，故由本任务带入）
- 分支：`zcode/dc12r1-mvp-l1-ct1-h2b-current-truth-sync-2026-08-26`
- 授权文件：恰 4 个（见 §5），零产品源码/测试/迁移/依赖变更。

## 1. 同步的当前真相

1. Current reviewed product baseline 更新为完整 SHA
   `436d61e2dfed88a9469e4572615b98b9c4a7aed4`（原记载 `a29f8db0` 为历史祖先）。
2. Last updated 更新为 2026-08-26。
3. 新增 H2-B `MERGED_AND_BROWSER_VERIFIED` 状态与证据链：
   - source `25626f4d9245a9b15cce92300fcdff8a5eb95de9`
   - Kilo 评审 `d6289a6b663a9c30851647776a3371508ee5ecc9`
   - 后端权威 `90f96e3ffdbc9071b8847893f1a0f009fd96afc4`
   - 浏览器 E1 `04134016485bf0679f46a73306d4c688c42d04ae`
   - merge `436d61e2dfed88a9469e4572615b98b9c4a7aed4`（parents
     `6e9470a1` + `25626f4d`，tree 与 source 逐字节相等）
   - merge report `c400b7c5747ebaf184cf1b82a5ac627dedc2dc3a`
4. 后端权威结果：3773 collected / 3710 passed / 48 skipped / 15 xfailed /
   zero red（failures/errors/xpassed 全零）。
5. 浏览器权威结果：24/24 browser PASS，29 节点 inventory 对账 gap=0
   （24 browser + 5 non-browser）。

## 2. 明确关闭项（写入 CTO_CURRENT_OPS / PROJECT）

1. 批发商忘记/重置密码链路（含 `j1h2b-forgot-reset` 中立性 harness）。
2. 匿名 reset 401 不再错误跳转登录页。
3. 多副本密码重置 token 消费原子性。
4. 用户角色分配 `MissingGreenlet` 异步序列化缺陷（含钉死回归套件）。
5. 相应测试残留归因与临时数据库 teardown/稳定性修复。

## 3. 保留的已知债务（如实保留，不声称关闭）

1. full-suite post-state 4/0/29 测试卫生债务（4 wholesalers / 0
   registrations / 29 uuid schema；外部归因，模块净贡献为零，重放恢复 0/0/0）。
2. `RT0 = BLOCKED_BY_H2_C`（零售商发现层缺失；禁止 API 绕过）。
3. `REMOTE_ENFORCEMENT_NOT_VERIFIED`。
4. 未部署、未完成 VPS/真机验收；不声称 deployed、customer-ready 或
   release-approved。

## 4. 预交付队列同步

由 PLANNING_SOURCE `addda5b6` 带入当前基线并按 CTO 2026-08-26 决策更新顺序：

`H2-C` → `PRICING-R0` → `PRICING-R1` → `ORDER-PRICE-R1` → `REORDER-R1`
→ `SKU-R0` → 首次使用引导 → 全业务旅程/VPS/真机终验

- 原 `H2-B-R3-R2` 第 1 项已完成受控合并，从队列移除，`H2-C` 递补第 1 项。
- 国家/货币口径：`FINANCE_LOCALIZATION_R0 = AUDIT_ONLY_NON_BLOCKING`；
  Uganda/UGX 与多币种暂不阻塞 MVP。
- 自定义 SKU 字段保持 `POST_MVP_DISCOVERY`。
- 队列为规划真相，不构成实现授权；每个条目仍需独立 CTO 门。

## 5. 变更清单（恰 4 文件）

1. `docs/ai/CTO_CURRENT_OPS.md` — 基线、H2-B 状态与证据、关闭项、
   债务、Active Phase、交付计划、Agent 分配、Stop Conditions。
2. `docs/ai/PROJECT.md` — 头部状态、分支映射、能力表、里程碑、验证快照、
   交付阻断与债务、有序工作计划。
3. `docs/planning/2026-08-26_mvp_pre_delivery_execution_queue.md` —
   新增（自 PLANNING_SOURCE 带入并更新顺序）。相对规划源的冻结输入差异
   （CT1-R1 勘误后精确表述）：第 3、4 节原文不变；第 5 节原有决策条目
   未删除或改变语义，但新增 custom-SKU = `POST_MVP_DISCOVERY` 与
   `FINANCE_LOCALIZATION_R0 = AUDIT_ONLY_NON_BLOCKING` 两项范围注释。
   不声称第 5 节字节一致。
4. `ai-ledger/product-ai/2026-08-26_dc12r1_mvp_l1_h2b_current_truth_sync.md`
   — 本台账。

历史纪律：未重写任何历史报告；所有历史合并（`6e9470a1`、`c5b66d26`、
`a29f8db0`、`ea990826`、`a6ef3aac`、`adcc7f28` 等）均明确标注为当前 tip 的
祖先而非当前 tip。

## 6. 质量门结果

- `git diff --check`：干净。
- detect-secrets（scoped pre-commit，含 `.secrets.baseline`）：Passed。
- 4 文件严格 UTF-8 / 无 BOM。
- 链接与 SHA 存在性核对：文中引用的 `436d61e2`、`25626f4d`、`d6289a6b`、
  `90f96e3f`、`04134016`、`c400b7c5`、`addda5b6`、`6e9470a1` 均为仓库内
  存在且经 `git cat-file -e` 验证的对象；引用的文档路径均存在。
- GitNexus detect_changes/analyze/status：索引于本分支提交重建，
  变更文件恰为 4 个授权文件。
- 未修改产品源码、未运行测试、未部署、未启动 H2-C。

## 7. CT1-R1 勘误（2026-08-26，规划证据措辞真相收口）

- 勘误对象：本台账 §5 第 3 条原表述"冻结输入 3-5 节保持不变"不精确，
  现予撤回并替换为上文的精确差异表述。
- 事实核对（`git diff addda5b6..HEAD -- docs/planning/…queue.md`）：
  第 3、4 节原文不变；第 5 节原有决策条目未删除或改变语义，
  但新增 custom-SKU = `POST_MVP_DISCOVERY` 与
  `FINANCE_LOCALIZATION_R0 = AUDIT_ONLY_NON_BLOCKING` 两项范围注释
  （前者附加于既有"无限 SKU 自定义属性"条目，后者为新增条目）。
  不声称第 5 节字节一致。
- 勘误边界：CT1 的产品状态记载、预交付队列顺序与实现范围均未改变；
  仅修正规划源差异的证据措辞；未修改另外三个 CT1 文件、产品源码、
  测试或任何历史报告。
- 勘误提交分支：`zcode/dc12r1-mvp-l1-ct1-r1-planning-evidence-wording-2026-08-26`
  （父提交 = CT1 提交 `ede56edc`；delta 恰为本台账 1 个文件）。

## 8. 裁决

ORIGINAL_CT1_VERDICT: **PASS_FOR_CTO_DC12R1_MVP_L1_CT1_H2B_CURRENT_TRUTH_SYNC**

声明上限（CLAIM_CEILING）：`CURRENT_TRUTH_DOCUMENTATION_PASS`。
本任务仅为文档真相同步；等待 CTO 审阅本分支并将当前真相并入受保护基线。

FINAL VERDICT（DC-12R1-MVP-L1-CT1-R1，规划证据措辞真相收口，
E1 元数据收口后生效）:
**PASS_FOR_CTO_DC12R1_MVP_L1_CT1_R1_PLANNING_EVIDENCE_WORDING_CLOSURE**

声明上限（CLAIM_CEILING）继续为：`CURRENT_TRUTH_DOCUMENTATION_PASS`。
CT1-R1 仅修正本台账 §5 的规划源差异证据措辞（见 §7 勘误），不改变
CT1 的产品状态、队列顺序或实现范围。
