# CTO_CORRECTION_E1 — 证据修正与更正声明

AUTHORIZATION_ID: CTO-AUTH-SKU-VPS-V4-R1-EVIDENCE-CORRECTION-E1-2026-09-13
EXECUTOR: Zcode-W | TIER: V3_SOURCE_AND_EVIDENCE_RECONCILIATION | DATE: 2026-09-13
冻结对象: CANDIDATE=1ee75d9f… / TREE=5712eb85… / PRODUCT_BASELINE=bd2373cb… / BASE_REPORT=58555700…
审阅依据: AI_REPORT_INBOX/sku-delivery-vps-cto-review-2026-09-13/CTO_REVIEW.md(处置:NEED_CHANGES_FOR_SKU_DELIVERY_ACCEPTANCE)

本文件按 CTO_REVIEW 五项 findings(§F1–F5)对初版 REPORT.md(7e47da80,证据 58555700)逐项更正。原始文本保留于本文件之前的 git 历史,不删改;更正处已在 REPORT.md 对应位置插入醒目引用。

---

## E1-1 交付范围更正(对应 CTO F1)

- 初版 REPORT 以 **50f15ded(前候选)..1ee75d9f(候选)** 为比较端点(76 路径,即最后一轮 R2 夹具修复轮),并在报告中声称"候选差分无前端路径 / BROWSER_RUNTIME NOT_RUN"。该端点选择**错误**:它只覆盖最后一轮修复,不代表整体交付。
- 独立复算 **PRODUCT_BASELINE..CANDIDATE(bd2373cb..1ee75d9f)= 130 路径**,与 CTO 实测一致。顶层分布:backend 59、**sku-m1-browser 26**、**frontend 16**、harness-governance 15、docs 7、ai-ledger 6、.secrets.baseline 1。
- **撤回**"候选无前端变更"的结论。16 个前端路径如实列举:frontend/src/pages/client/{CreateOrderPage,ProductDetailPage,ProductListPage}.tsx、frontend/src/pages/orders/CreateOrderPage.tsx、frontend/src/pages/skus/{AddSellableUnitModal,SKUFormModal,SKUListPage}.tsx、frontend/src/services/{catalogProductService,skuService}.ts、frontend/src/tests/{ClientMultipackaging,S5BRealUserSmoke,SKUCatalogIdentity.integration,SKUCatalogIdentity,SKUListPage}.test.tsx、frontend/src/types/{client,order}.ts。
- 范围对账:**累计交付范围**=130 路径(上表);**最后一轮修复范围**=50f15ded..1ee75d9f(R2 夹具隔离:backend/tests/test_sku_bc06_reprice_guard.py、harness-governance/inventory/protocol-deltas.json、ai-ledger R2 台账)。
- 因此 BROWSER_RUNTIME=NOT_RUN 的理由(前端不在范围内)不成立;前端与浏览器旅程列为**未验证交付缺口**,补验计划见 REMAINING_VALIDATION_PLAN.md G1。

## E1-2 三层交付覆盖对账(对应 CTO F2/F4 覆盖部分)

| 交付要求 | 真实测试/证据 | 状态 |
|---|---|---|
| 稳定内部身份(M1) | backend/tests/test_sku_m1_catalog_identity.py | **本轮执行**(F2,140 passed 内) |
| API RBAC/租户隔离(M1) | backend/tests/test_sku_m1_api_rbac.py | **本轮执行**(F2) |
| 包装与序列化闭包(B2) | backend/tests/test_sku_b2_catalog_serialization.py + 变异门 | **本轮执行**(F2;变异见 E1-3) |
| BC-06 重定价守卫(历史引用/软删除竞态/锁后新鲜读/定价保护) | test_sku_bc06_reprice_guard.py(37 节点,真实 PG,双连接+事件屏障) | **本轮执行**(F1) |
| 订单快照保持 | test_order_creation.py、test_orders_api.py、test_phase4_pricing_safe_orders.py | **本轮执行**(F2) |
| 导入/intake 竞态(409 SKU_EXISTS) | test_u3c_import_apply.py、test_u4c_intake_api_contract.py | **本轮执行**(F2) |
| 迁移 038(新库/已有租户/legacy/库存初始化/失败窗口) | test_sku_m1_migration_pg16.py(PG16.15 真实升级)+ test_alembic_migrations.py | **本轮执行**(F3);完整 001→038 重放 NOT_RUN |
| 多重包装闭包(r1) | test_sku_r1_multipackaging_closure.py、test_sku_r1_client_catalog_contract.py | **本轮执行**(F2) |
| 前端客户旅程(客户端目录/详情/下单 + 员工 SKU 页) | sku-m1-browser(B1–B4 Playwright 冻结夹具)+ frontend/src/tests/* | **未验证**(候选树零运行);历史台账(ai-ledger 2026-08-31 B1–B4)基于更早基线,未与候选逐字节绑定,仅作历史参考 |
| 结构/治理门(protocol-deltas、runbook oracle) | harness-governance(49 门) | 历史证据引用(候选树内置;本轮未重跑) |

注:上表"本轮执行"仅指 VPS V4 运行中真实执行并 GREEN,不外推为生产认证或真实 JWT 客户旅程通过(见 E1-8)。

## E1-3 变异结果更正(对应 CTO F3)

按原始日志(formal-5-mutations.txt + formal-5-m03-dynamic.txt)重新分类,**显式取代初版报告 F5 段与门禁聚合措辞**:

- **动态杀死 = 4**:M01(移除 post-flush reload)、M02(移除 populate_existing)、M04(返回过期 pre-reload 产品)、M05(省略 updated_at 序列化)——各产生语义 RED,逐字节恢复,复跑 GREEN。
- **静态检查 = 2**:M03(selectinload 出现次数==3 的存在性守卫,**未应用任何移除**)、M06(测试断言锚点存在性守卫)。
- **补充动态证伪 = M03 变异存活**:手工移除全部 3 处 loader(语法校验通过)后 b2 套件 **9 passed——变异未被杀死**。与 runner 文档串声称的 "T2 RED with MissingGreenlet" 不符。
- 因此初版门禁聚合 "all mutations RED as intended" 对 M03 为**过度声明**,予以取代。存活的原因表述限定为:"该 9 节点在无 eager loader 下行为不变;后置 reload 是否构成全路径冗余**未证明**"(初版 ADDENDUM 中 "redundant belt-and-suspenders" 的措辞相应弱化)。
- runner 的错误聚合登记为**待修工具缺陷**(建议:动态 M03 实现行为表达型断言或重新分类);本轮不改源码。

## E1-4 正式续跑事实完整记录(对应 CTO F2)

准备阶段(A1–A7 + 陷阱实现)与正式阶段(F1–F6)按 attempts.log 当时记录区分,未事后改名。运行环境身份与逐次尝试:

| 运行 | 起止(+08:00) | 命令(冻结形式) | 退出码 | PG 版本 | 角色 | Redis |
|---|---|---|---|---|---|---|
| F1-a1 | 09-13 ~11:45 | pytest tests/test_sku_bc06_reprice_guard.py | 1(环境:库不存在) | PG15(镜像 postgres:15-alpine,运行版本未捕获) | sku_task 已建 | 16379/0 |
| F1-a2 | ~11:47 | 同上 | 1(环境:迁移缺 REPORTING_USER_PASSWORD) | 同上 | 同上 | 同上 |
| F1-a3 | ~11:48 | 同上 | 1(环境:角色缺 CREATEROLE→已授权,rolsuper 仍 false) | 同上 | 同上 | 同上 |
| **F1-a4** | 11:48–11:49 | 同上 | **0,37/37** | 同上 | 同上 | 同上 |
| F2 | 11:50:06(+42s) | pytest <11 回归模块> | **0,140 passed** | PG15 同栈 | 同上 | 同上 |
| F3-a1 | 11:50:48(+1s) | pytest test_alembic_migrations.py test_sku_m1_migration_pg16.py | 1(**环境**:临时库端口未列入允许 + 栈为 PG15) | PG15 | 同上 | 同上 |
| (PG16 栈供应) | 11:53:00 | 拉取/启动 sku-r2-pg16 @127.0.0.1:15433 | — | **PostgreSQL 16.15** | 同角色重建 | 同上 |
| **F3-a2** | ~11:53:30(+14s) | 同 F3 | **0,10 passed 3 skipped** | **PG16.15** | 同上 | 同上 |
| F4-a1 | 11:54:32–~12:18 | pytest tests/(全量 3883) | 1(**3× TooManyConnections + 1× 限流断言**,见 E1-5) | PG15,max_connections=100 | 同上 | 同上 |
| F4-a2 | 12:29:35 启动,12:36 停止 | 同上 | 无(清理打断,无 .done;部分输出留存 VPS,未发布) | PG15,max_connections=400 | 同上 | 同上 |
| F4-a3 | 12:36:32–12:54:08 | 同上 | 1(1× 限流断言:PW1R3_TEST_REDIS_URL 缺省 26379/15 未供应) | PG15,max_connections=400 | 同上 | 同上 |
| F4-R 限流模块 | 12:57:28(+6.5s) | pytest tests/test_pw1r3_rate_limit_context.py | **0,7 passed** | 同上 | 同上 | **16379/15(PW1R3 专用)** |
| **F4-a4(最终)** | 12:57:36–13:15:15 | 同 F4-a3 含 PW1R3 env | **0,3839 passed 29 skipped 15 xfailed** | PG15,max_connections=400 | 同上 | 同上 |

- PG15 运行版本:UNKNOWN(仅记录镜像 tag postgres:15-alpine 与 digest,见 evidence/images/run-manifest.json;运行时版本串未捕获)。
- PG16 运行版本:16.15(attempts.log F3 供应段)。**F3 的 PG16 证据不外推至 F1/F2/F4(三者在 PG15 栈执行)。**
- 缺号解释:F4 无 attempt 编号跳跃——a1(RED 保留)、a2(清理打断,无结果)、a3(1 失败)、a4(最终 GREEN)。
- **授权偏差登记**:F3-a1 与 F4-a1 出现 RED 后未停止验收,而是环境修正后继续——按当时判断为"准备/环境修正",现按 CTO 要求登记为对冻结 STOP 规则的**授权偏差**;全部原始输出保留于 evidence/full-suite/。
- 配置变化清单:max_connections 100→400(a2 前);临时库端口允许清单 MPANGO_TEMP_DB_ALLOWED_PORTS=15432/15433 分栈设置;PW1R3_TEST_REDIS_URL=redis://127.0.0.1:16379/15(a4 前追加);角色能力最终态 NOSUPERUSER+CREATEDB+CREATEROLE(FIX3)。

## E1-5 失败归因更正(对应 CTO F4)

F4-a1 的 4 个失败逐节点对应(保留日志 formal-4-attempt1-conn-exhausted.txt):

1. tests/test_s4_jobs_local.py::test_enqueue_job — asyncpg TooManyConnectionsError
2. tests/test_s4_jobs_local.py::test_job_execution — asyncpg TooManyConnectionsError
3. tests/test_s4_jobs_local.py::test_job_execution_with_delay — asyncpg TooManyConnectionsError
4. tests/test_pw1r3_rate_limit_context.py::test_101st_anonymous_is_429_… — AssertionError(first_429=None,预期 101)

初版"均为连接耗尽"的表述**更正**为"3 个连接耗尽 + 1 个限流断言失败"。max_connections=400 后 GREEN 仅证明**该配置下通过**;缺少连接生命周期证据(无连接级采样/审计),容量不足与连接生命周期缺陷两种根因**均未排除**,保留为未完全证明。

## E1-6 SKIP/XFAIL 与迁移边界补全(对应 CTO F4)

- 机器化模块级分布(node-outcome-inventory.json,自保留日志解析,合计与冻结汇总一致):**29 SKIP / 15 XFAIL 的逐节点名 UNKNOWN**——冻结运行采用 -q 模式未逐项列出;源码声明级清单如下,精确运行节点集合标记 UNKNOWN。
- F3 的 3 个 SKIP(逐字引用):`pytest.skip("Requires running Alembic CLI - integration test")` × 3(test_alembic_migrations.py 三个 CLI 集成骨架)——**未实现的 Alembic CLI 集成骨架**,如实登记。
- 源码声明级 skip 计数(静态,top):test_route_coverage 6、test_request_validation 6、test_s3b_fresh_tenant_live_runtime_proof 3、test_platform_p21e/p21dd/p21_adapter 各 3、test_alembic_migrations 3、其余 1–2;运行时 29 SKIP 与静态声明的对应关系为部分推导,标记 UNKNOWN。
- 15 XFAIL 的逐节点清单 UNKNOWN(源码 xfail 声明扫描见后续可补交)。
- 迁移边界:真实升级测试(test_sku_m1_migration_pg16,PG16.15)与结构检查(test_alembic_migrations 的非 skip 部分)已分列;**完整 001→038 重放 NOT_RUN**(维持)。

## E1-7 证据发布与 MISSING 登记(对应 CTO F5)

本次新增发布(均经脱敏检查:任务密码 0 残留):evidence/prep/attempts.log(19,897 字节完整尝试日志)、evidence/cleanup.sh、evidence/hashes.txt、evidence/node-outcome-inventory.json、evidence/timeline.txt、evidence/secrets-scan-changed.json、evidence/baseline-before/after.txt、full-suite 四轮完整输出、acceptance-checklist.md、run-manifest.json、pip-freeze.txt。
来源哈希(evidence/hashes.txt,VPS 侧生成):cleanup.sh=9b5aac2e…、acceptance-checklist(aea3f303…,E1 前版本)、pip-freeze=8602a95f…;published-attempts.log 的 sha256 见本次提交后 evidence/hashes-e1.txt。
**MISSING 登记**:F4-a2 部分输出(保留于 VPS results/,未随包发布);Q3-STOP-REPORT.md(见下);PG15 运行时版本串。以上不重建、不补造。
**Q3 更正**:初版引用 M0 STOP_REPORT(2026-09-03)为替代,CTO 判定不构成替代。真实 Q3-STOP-REPORT.md 在候选树/远端/报告目录未定位——登记为 **MISSING(待 Codex-L/CTO 提供路径或文本;如采用用户提供文本,将标注"转录,未核对远端原件")**。

## E1-8 独立性声明更正(对应 CTO F5/治理)

- 累计候选(bd2373cb..1ee75d9f)的提交谱系含 **Zcode-W 执行的历史轮次**:BC-06 R2(50f15ded 的前身提交)与 R2-R1(50f15ded 本身,git 作者身份 dfljeff01-commits,轮次报告明确 EXECUTOR: ZCode-W)。
- 因此本轮 V4 运行中,F1(BC-06 37 节点)与 F2 内 BC-06 相关路径验证的是**含 Zcode-W 历史 authored 变更的代码**——存在作者重叠,**不能声称完全独立审查**;独立性定级与补充审查范围由 CTO 决定。
- 其余大部分提交的 git 作者身份为 "Vibecoder AI"(按台账对应 Codex-L 执行轮次)。
- **MPANGO_ENV=test 限定**:全部套件在该模式下运行(conftest 选择 MockAuthStrategy、确定性测试 SECRET_KEY);结论不泛化为真实 JWT 生产认证客户旅程通过。

## 结论(在 CLAIM_CEILING 内)

EVIDENCE_CORRECTION_COMPLETE_PENDING_CTO_REVIEW。本轮为证据修正与对账,不新增任何产品/测试/依赖/基线/runner 修改;候选零改动(worktree 仅 reports/ 变更)。剩余缺口与最小补验计划见 REMAINING_VALIDATION_PLAN.md。PRODUCT_ACCEPTANCE=NOT_GRANTED;NEXT_GATE=CTO_TARGETED_VALIDATION_SCOPE_DECISION。
