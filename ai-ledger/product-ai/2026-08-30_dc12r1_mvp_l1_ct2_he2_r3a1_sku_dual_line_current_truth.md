# DC-12R1-MVP-L1-CT2 - HE2 R3+A1 与 SKU 双线当前真值同步

- 日期：2026-08-30（+08:00）
- 执行者：Codex acting as CTO
- 任务：DC-12R1-MVP-L1-CT2
- 变更类别：`DOCS_ONLY_CURRENT_TRUTH`
- 验证层级：`V1_SOURCE`
- 声明上限：`CURRENT_TRUTH_DOCUMENTATION_PASS`
- 基线：`origin/product-dev-recovered@d9dc2e4130ea87a57d433dfadeb2f2736576fac6`
- 分支：`codex/dc12r1-mvp-l1-ct2-current-truth-sync-2026-08-30`
- 授权范围：两份 CTO 当前真值文档、预交付队列和本台账；产品 delta 为零。

## 1. 已接受的基线变化

HE2 R3+A1 受控治理合并已进入 `product-dev-recovered`：

- source：`483b8ab01dae41d52404ebfe197e205a16d56e85`
- Kilo final：`db87f0d3eb55d4ff60b82b22f392db457a66a780`
- Lubuntu fresh-runtime final：`6fb1e31e8e92a5d365270ceb72b4982dd7f4c1ca`
- merge：`d9dc2e4130ea87a57d433dfadeb2f2736576fac6`
- merge report：`1017be0c7b8f08e96c5ae3eea03b29985ca0749e`

合并只修改 `harness-governance/`。当前产品 Alembic head 仍是
`037_payment_declarations_schema`。新的受保护 authority profile 可以在未来
SKU 候选中精确授权 `038_catalog_identity_vertical_slice`，并要求其 parent
精确为 `037`；profile 的存在不等于迁移 `038` 已实现、运行或合并。

## 2. HE2 关闭项

1. backend authority 在执行前绑定规范 CWD、`MPANGO_ENV`、安全测试数据库名、
   host 和 temp-DB port allowlist。
2. runner 与 pytest child 独立复核；preflight 后漂移进入 VOID，权威命令零启动。
3. Alembic 权限来自受保护 profile 原始字节，不接受 CLI/env/proof 覆盖。
4. 精确 head、声明 parent 和单 head 受约束；错误 parent、多 head、相似前缀、
   多余空白和运行中漂移 fail closed。
5. Kilo 独立执行 186/186 和 102 RED / 9 GREEN；Lubuntu fresh runtime
   执行 core 8/8、Redis 7/7、17/17 负控 VOID。

## 3. 双线执行决策

严格串行的旧队列被更新为两个独立的 V3 产品线：

1. H2-C 线：由 Zcode/Windows 负责当前基线集成与有界修正；重新完成有效
   backend authority 和权威浏览器旅程。
2. SKU-R0-M1-R1 线：由 Codex-L 负责架构、实现、内部审查与候选真实性；
   OpenCode2 独立复核源码、迁移、fresh runtime 和浏览器证据。

两条线不得共享候选、运行时或 PASS。只有两条线分别完成受控合并，才允许进入
`PRICING-R0`。此并行授权用于提前关闭定价和再次下单依赖的稳定商品/包装身份，
不是对价格、订单调价、再次下单、支付、税务或促销实现的提前授权。

## 4. H2-C 当前真值

- integration candidate：`42c5d3286cacaf48604550eecd881e379cc76818`
- 原 Lubuntu 报告：`0f6f790b11a3c2a316fc276df727fa19271b3616`
- evidence-truth correction：`31adf4922087b0f719ba72ffd89e4e89c76f189e`
- 有效分类：`VOID_ENVIRONMENT_PRECHECK`
- 浏览器：`NOT_RUN`
- 合并状态：未合并

因此 `RT0 = BLOCKED_BY_H2_C` 保持有效。旧候选不得直接晋级；必须在当前基线
重新集成并通过有效权威门。

## 5. SKU-M1 当前真值

- 旧 Codex-L 工作树包含实质性的三层 catalog identity 纵向实现，但未提交，
  `CANDIDATE = NONE_UNCOMMITTED`，只作为恢复输入。
- 旧实现因 HE2 固定 `037` 而 STOP；该治理阻塞现已由 R3+A1 关闭。
- CTO 已签发 L0-RESUME，要求从 `d9dc2e41` 建立新工作树，不得在旧工作树
  直接 rebase/commit。
- 冻结架构：`CatalogProduct -> SellableUnit -> CatalogOffer boundary`。
- 本轮 SKU 范围：稳定产品/包装身份、不可复用 code、订单行稳定 UUID 与不可变
  快照、历史 legacy 不猜测回填、产品级多包装 UX。
- 已识别且必须在候选前关闭：增加包装的 RBAC 错配、扁平 SKU 列表未形成产品级
  UX、新 catalog 创建路径的 inventory stock 初始化合同，以及真实 PG migration、
  full backend、390px/browser 和独立审查证据缺失。

没有 SKU candidate、没有迁移 `038` PASS、没有 full-suite PASS、没有浏览器 PASS、
没有 merge-ready 或 deployment-ready 声明。

## 6. 保留债务与停止边界

1. release validator 仍因 `DEBT-AUTH-CRITICAL-TUPLES` 与
   `DEBT-COMMERCE-CRITICAL-TUPLES` 返回 exit 3。
2. `RT0 = BLOCKED_BY_H2_C`。
3. `REMOTE_ENFORCEMENT_NOT_VERIFIED`。
4. 未部署、未完成 VPS/HTTPS/真机/真实邮箱最终验收。
5. SKU 不得扩展到定价、订单生命周期、支付、税务、促销或客户特别价。
6. 迁移 `038` 如不是精确 `038 -> 037` 单 head，或不能证明 all-tenant preflight、
   rollback/零部分 mutation、bootstrap parity 和 legacy 不猜测回填，必须 STOP。
7. 任一 authority preflight 失败后的测试运行均为 `VOID_ENVIRONMENT_PRECHECK`，
   不具产品归因效力。

## 7. 文档变更范围

1. `docs/ai/CTO_CURRENT_OPS.md`
2. `docs/ai/PROJECT.md`
3. `docs/planning/2026-08-26_mvp_pre_delivery_execution_queue.md`
4. 本台账

未修改产品源码、测试、迁移、依赖、锁文件、部署文件或治理运行器；未运行产品
测试、PG、Redis、Playwright 或部署。

## 8. 文档质量门

- 精确变更范围：4 个授权文档文件，产品/测试/迁移/依赖/治理代码零变化。
- `git diff --check`：PASS。
- scoped pre-commit：trailing whitespace、EOF、large-file 和 detect-secrets
  全部 PASS。
- 4 文件严格 UTF-8、无 BOM、无 NUL、无 CR、无 U+FFFD。
- 8 个关键证据 SHA 均通过 `git cat-file -e <sha>^{commit}`。
- GitNexus 1.5.3：indexed commit == current commit `d9dc2e4`，status up-to-date。
- GitNexus `detect_changes(scope=all)`：3 个已索引文档、44 个文档符号、0 个受影响
  流程，风险为 low；新增台账不在当前文档索引符号集内。
- 未运行产品测试、PostgreSQL、Redis、Playwright 或部署。

## 9. 裁决

`PASS_FOR_CTO_DC12R1_MVP_L1_CT2_HE2_R3A1_SKU_DUAL_LINE_CURRENT_TRUTH_SYNC`

该裁决只表示文档与已接受证据同步，不构成 H2-C、SKU、定价、合并、部署或发布
批准。
