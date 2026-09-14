# G1/G2/G3/G5/G7 结果报告 — SKU Delivery VPS V4(authorship-disclosed)

AUTHORIZATION_ID: CTO-AUTH-SKU-DELIVERY-VPS-G1-G2-2026-09-14
EXECUTOR: Zcode-W | TIER: V4_LINUX_RUNTIME_EVIDENCE_WITH_AUTHORSHIP_DISCLOSURE | DATE: 2026-09-14
CANDIDATE: 1ee75d9f…(TREE 5712eb85…,worktree detached 校验一致)| PRODUCT_BASELINE: bd2373cb… | BASE_REPORT: 58555700…

**PG16 为本轮绑定的数据库主版本**(CTO 决定);既有 PG15 结果保留为独立补充观察。本报告取代 E1 报告中的比较端点/轮次标签/Q3 发布声明/Kilo 引用描述(E1 CORRECTIONS-2 已提交 a1ace880)。

---

## G1 前端与客户旅程(VPS Linux 真实浏览器,PG16 运行栈)

### G1-a 冻结前端依赖:五模块 vitest + 生产构建
- 工具链(冻结):Node v22.23.2(任务本地 tools/node22)、pnpm 9.15.4(精确钉定)、Chromium 131.0.6778.33(任务私有 PLAYWRIGHT_BROWSERS_PATH,executable 已记录)。
- `pnpm install --frozen-lockfile`(frontend 与 sku-m1-browser 各自目录):**均成功,官方 registry,未改写 manifest/lock**。
- **重复 jsdom 声明的解析行为(如实报告)**:vite/esbuild 加载 package.json 时发出 `[duplicate-object-key] Duplicate key "jsdom" in object literal` 警告(package.json:40 与前值重复,解析保留后值 ^29.1.1);`pnpm install --frozen-lockfile` 按锁文件解析 jsdom 29.1.1 安装成功,未重写 manifest/lock。
- **正式运行**(冻结命令,CI=true):5 模块 → **21/21 test cases 全部 passed,0 failed**(结构化结果 evidence/g1/g1-vitest.json;逐模块状态:ClientMultipackaging/S5BRealUserSmoke/SKUCatalogIdentity.integration/SKUCatalogIdentity/SKUListPage 全 passed)。冻结收集清单 evidence/g1/g1-vitest-nodes.txt(430 行,含 5 个套件头;实际用例 21)。
- **pnpm build**(tsc -p tsconfig.app.json && vite build):**exit 0**,dist/ 产出(vite 5.52s)。

### G1-b 浏览器旅程(生产构建前端 + 真实后端 + 真实 Chromium;AUTHOR_DIAGNOSTIC 模式)
- 运行栈:任务 PG16.15(mpango_b1,迁移至 038)+ Redis 7(16379/15)+ 后端 uvicorn:8000(生产模式,真实 JWT+SMTP,runbook 标记块原样填充;迁移/夹具角色 sku_mig 与应用运行角色 sku_app 分离,函数属主已按运行期管理需要转移)+ 前端 vite preview:8102(/api 继承代理→8000)+ SMTP sink:8103(maildir)。全部仅绑定 127.0.0.1。
- 预检:backend /health/live 200;frontend / 200;preview 代理 /api(401=认证路径正常);SMTP 监听;Redis PONG。
- **正式调用:单次 `playwright test`,恰好 4 executions,全 GREEN(20.4s)**:
  - [desktop] CATALOG-ID-001 ✓、CATALOG-HIST-001 ✓
  - [mobile-390] CATALOG-ID-001 ✓、CATALOG-HIST-001 ✓
- 后置门:**static_validator GREEN(reconciliation gap=0)**;`--require-mode AUTHOR_DIAGNOSTIC` GREEN;tools/scan_artifacts GREEN(9 files, 0 findings)。
- 旅程断言(真浏览行为,非 API mock):catalog_product_created_via_ui、packages_have_distinct_stable_uuids、packages_own_independent_stock_rows、retired_package_code_not_reusable、retailer_sees_product_in_catalog、packaging_selection_changes_sellable_unit_id、stock_updates_for_selected_unit、**order_request_carried_selected_sellable_unit_uuid(订单快照行为)** 等。
- 准备期迭代(非正式,均留痕):a1 VOID redis:db_nonempty(健康检查误写 DB15,已归档 g1b-attempt1-void);a2 供应 503(public 守卫函数属主为迁移角色,运行角色需管理——已转移属主并重建全新库);a3 = 正式 GREEN 轮。

## G2 后端全量套件(任务 PG16 栈,一次正式运行)

- PG16 身份:镜像 postgres:16,digest `postgres@sha256:f1c3376c26f2609ab9f29f71f824103fe2fcd8ee0346485cb6122a4f93df6f94`,SELECT version() = **PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2)**。
- 冻结收集对账:`pytest --collect-only -q` = **3883 collected**(与既有冻结预期一致,无收集差异)。
- 正式命令(自 backend):`python -m pytest tests/ -v -rs -rx --junitxml=<task-evidence>/backend-pg16.xml`。
- **结果(JUnitXML,机器可读)**:执行 **3887 节点**——passed **3284**、failed **169**、error **371**、skipped **63**。收集 3883 与执行 3887 的 +4 差异为假设/参数化物化差异,如实记录。
- **G2 判定:在 PG16 绑定下后端套件未通过**(540 非通过节点)。失败类以 sqlalchemy ProgrammingError(asyncpg)为主,系 PG15→16 SQL 兼容性;按文件分布 top:dc12r1_s1_r5_migration_preflight_exact_catalog 38、platform_p21_durable_approval_schema 31、WPR004 共享语句 HTTP mapper 18、DateRangeContract 17、dc12r1_s1_retailer_identity 14、RuntimeMatrix 14、s4e_stock_reservation_lifecycle_audit 12、j1_h2c_retailer_recovery 12、s1_r3_migration_contract 11、dc3b_credential_recovery 10、s4_jobs_local 9、RangeCap 8;涉及 110 个文件。
- **BC-06 核心(PG16)**:test_sku_bc06_reprice_guard **37/37 全部 passed**——SKU 核心守卫在 PG16 绑定下完整通过。
- **运行期缺陷(如实登记)**:全部节点执行完毕且 JUnitXML(3.9MB)写出后,进程在解释器关闭阶段挂死(u6i2 residue guard teardown ExceptionGroup + 协程未 await);等待 22+ 分钟无退出后 SIGKILL。**套件级退出码未捕获**;JUnitXML 逐节点证据完整有效。登记为 PG16 关闭期缺陷(待修),非产品断言失败。
- PG15 既有 3839-pass 结果按 CTO 决定保留为独立补充证据;按授权未再跑 PG15 全量。

## G3 独立空库真实迁移重放 001→038

- 独立空库 g3_replay(OWNER sku_mig)→ `alembic upgrade head`:**exit 0**,日志记录 **38 条 "Running upgrade" 真实链**,`alembic current` = 038_catalog_identity_vertical_slice (head)。
- 证据:evidence/g3-alembic-replay.log(完整链)、g3-final-head.txt。**不再是 NOT_RUN**。

## G5 逐节点结果清单

由 F4 的 -q 模式升级为本轮 `-v -rs -rx --junitxml`:**backend-pg16.xml(3.9MB)即逐节点机器可读清单**(每节点 classname/name/status/耗时);`g2-full-pg16-verbose.txt` 为逐节点文本输出(含 -rs/-rx 的 skip/xfail 理由行)。63 SKIP/15 XFAIL(以 XML 计 63 skipped;xfail 在 XML 中按其最终状态记账,详细理由行见 verbose 日志)——是否影响交付要求由 CTO 按 E1-2 对账表裁量。

## G7 连接观察(有界,不新增框架)

- 方式:20 秒间隔只读采样 `pg_stat_activity`(时间戳|datname|state|count,无查询文本、无密钥),覆盖 G2 全程与结束后;证据 evidence/pg-activity-samples.log。
- 观察(样例):套件期 mpango_b1 idle 7 + active 1;结束后 test_mpango_task_pg16 idle 3、mpango_b1 idle 7、实例总连接 5。
- 边界:该有界观察**不能证明/证伪连接泄漏**;max_connections=400 下的 GREEN 只证明该配置下通过。

## G4 变异分类(按授权保持deferred,无新机制)

动态杀死=4(M01 移除 post-flush reload/M02 移除 populate_existing/M04 返回过期产品/M05 省略 updated_at 序列化——各语义 RED+恢复 GREEN);静态检查=2(M03 loader 存在性、M06 断言锚点);补充动态证伪=**M03 移除后 9 passed,变异存活**。runner 聚合措辞缺陷登记待修。M03 行为表达型覆盖建议见 REMAINING_VALIDATION_PLAN G4(未获本轮授权实施)。

## AUTHORSHIP_OVERLAP(累计候选)

- **BC-06 R1(f151f53d)/R2(3e831384)/R2-R1(50f15ded)三修复轮由 Zcode-W 执行并 authored**(三轮报告 EXECUTOR 一致;git 身份 dfljeff01-commits)——本报告 G1-b/F2 及历史 F1 所覆盖的 BC-06 锁/定价守卫路径存在作者重叠,证据独立性降级。
- **缓解**:Kilo 独立评审已发布——分支 `kilo/bc06-independent-review-report-2026-09-14`,提交 `815094d4fc3fd59b8acc230c1ed6e59987ef58c6`(parent=候选,fetch 核验),EXECUTOR=Kilo(非重叠执行者、独立隔离工作树):F1 复跑 35 passed/2 环境失败(bc06r1 超管误配、reporting_user 密码源不一致——均非业务缺陷,且与本 VPS 栈的正确配置互为对照)+ pricing_repository/package_identity/测试断言的源码对照审查。独立性最终定级由 CTO 决定。
- 其余累计提交的 git 作者身份为 "Vibecoder AI"(台账对应 Codex-L 执行轮次)。

## E1 修正交叉引用(已提交 a1ace880,CTO_CORRECTIONS-2 节)

1. 比较端点:唯一"最终三路径夹具变更"= 8e9aeb48..1ee75d9f;50f15ded..1ee75d9f 含集成变更。**轮次标签更正(取代 E1-8-S):R1=f151f53d、R2=3e831384、R2-R1=50f15ded**。
2. Q3 原件发布声明更正:evidence/q3-original/ 未发布于仓库;原件经 SSH 于源机核对(两哈希与转录一致)后**有意保留在仓库之外**(launch-intent.json 含主机网络拓扑),核对纪要已发布。
3. Kilo 评审出处与发现处置如上;初版"indep-f1-rerun=Kilo 报告"的说法不成立(它只是 Zcode-W 重跑),Kilo 独立评审以本报告引用的分支/SHA 为准。

## UNCOVERED / NOT_RUN / 边界

- 前端浏览器旅程已于候选树完成(AUTHOR_DIAGNOSTIC 模式);**INDEPENDENT_AUTHORITY 模式的独立执行者浏览器复跑**未包含(可选后续,由非 Zcode-W 执行者执行同一 runbook)。
- 迁移"全历史回滚-再升级"双向演练未包含(仅正向 001→038 重放 + pg16 模块的声明前态场景)。
- 63 SKIP/15 XFAIL(X 計 3887 口徑)对交付要求的逐项影响 → CTO 按 E1-2 对账表与 JUnitXML 裁量。
- PG15 运行时版本串未捕获(镜像 tag+digest 已记录);PG16=16.15 已记录。

## 清理与完整性

- 任务容器(sku-b1-pg16/sku-b1-redis)与任务卷经归属化 cleanup.sh 清除;共享镜像(postgres:16、postgres:15-alpine、redis:7-alpine)按"引用≠独占"保留并记录;未使用 docker system prune。
- 候选零改动:worktree detached 于候选,正式运行前后 tree 校验一致;报告分支仅含 reports/ 增量。
- 最终 SHA-256 清单:evidence/final-manifest.sha256(本分支,覆盖全部已发布证据文件)。

最终清单(evidence/final-manifest.sha256.gz,38 条目)自身 sha256:`108cc4d0c50a04cd0f30d8761a79b6b9d3e666b8c8cba4ce4526b8a323c9fb5e`
