# REMAINING_VALIDATION_PLAN — 最小补验计划(E1 后)

AUTHORIZATION_ID: CTO-AUTH-SKU-VPS-V4-R1-EVIDENCE-CORRECTION-E1-2026-09-13(后续)
前置状态:EVIDENCE_CORRECTION_COMPLETE_PENDING_CTO_REVIEW | PRODUCT_ACCEPTANCE=NOT_GRANTED
原则:每个缺口只做针对性补验;不默认全量重来;任何重跑在新声明验收计划下进行。

| # | 交付要求 | 现有证据 | 缺失证明 | 建议命令/动作 | 环境与预计成本 |
|---|---|---|---|---|---|
| G1 P1 | 前端客户旅程 + SKU 浏览器交付(16 前端路径 + sku-m1-browser 26 路径) | 历史台账 B1–B4(更早基线,未与候选绑定);候选树含冻结 Playwright 夹具与前端测试 | 候选树上的浏览器旅程运行证据;前端 vitest 套件运行证据 | ① `frontend`: npx vitest run(5 个 *.test.tsx)② 按 runbook 运行 sku-m1-browser 冻结夹具(CATALOG-ID-001/CATALOG-HIST-001,桌面+390px)③ 对 16 前端路径做构建/类型门 | 任务 PG15/PG16 栈 + loopback SMTP sink(按 runbook);浏览器供应方式需 CTO 批准(VPS 无浏览器,建议 Windows 侧或临时容器)。约 1–2 小时 |
| G2 P1 | PG16 运行绑定决策 | F3(迁移+pg16 模块)在 PG16.15;F1/F2/F4 在 PG15(max_connections=400) | F1/F2/F4 在 PG16 下的等价结果(若 CTO 裁定 PG16 为运行绑定) | 若裁定 PG16 绑定:同一冻结命令在 15433 栈重跑 F1(37)+F2(140)+全量;若裁定 PG15 为生产对齐目标:在 REPORT 登记互补关系即可 | 任务 PG16 栈已验证可用;全量 ~18–24 分,F1+F2 ~5 分 |
| G3 P2 | 迁移完整链 001→038 | alembic history/current(最终头)+ pg16 模块内分场景升级 | 从空库一次性重放并记录逐版本链 | 全新临时库 `alembic upgrade head` + `alembic history`/逐步 `upgrade +1` 记录 | 任务 PG 栈;~10 分钟;脚本化即一次性 |
| G4 P2 | M03 行为覆盖(变异存活) | 静态守卫(3 loader 存在)+ 补证(移除后 9 passed 存活) | 行为表达型测试:如"序列化阶段零懒加载 SQL"断言(语句计数),或 Codex-L 重新分类 M03 为静态设计检查 | Codex-L 设计 + 实现于 b2 套件;复跑 F5 门 | b2 套件 ~1 分钟/次;设计 ~1–2 小时 |
| G5 P2 | 完整逐节点结果清单 | node-outcome-inventory.json(模块级;逐节点 PASSED 名 UNKNOWN) | -v/-rs 模式的逐节点 SKIP/XFAIL 名与理由 | 全量套件以 `-v -rs -rx` 重跑一次(仅记录用途) | 任务栈;~20–25 分;或接受模块级清单 + UNKNOWN |
| G6 P2(✅ 已完成 2026-09-13) | Q3 交付要求对齐 | 转录已发布且**原件哈希核对一致**(86cc99f8…/35b8671d…,evidence/q3-original/ 5 文件);Q3=本 VPS 授权直接前置,PRODUCT_RED=NO、RUNTIME=NOT_RUN,两陷阱与本轮 E1 修正互证 | 无剩余(原件核对已完成) | — | 已完成 |
| G7 P2 | F4 失败根因闭环(容量 vs 连接生命周期) | attempt1 traceback + 400 上限后 GREEN | 连接生命周期证据(池上标本/连接年龄/泄漏检测) | 若 CTO 要求:pool events + pg_stat_activity 采样重跑 s4_jobs_local 模块 | 任务栈;~20 分钟 |

全量重跑说明:F4-attempt4 已为环境完整条件下的 GREEN 实测;仅当 CTO 裁定 G2 需 PG16 全量绑定、或 G5 要求逐节点清单时,才需要再次全量;否则定点补验(G1/G3/G4)+ 既有 3839-pass 事实即可支撑验收决议。

扫描与完整性:本轮新增证据已过 detect-secrets(负控有效)与基线 sha256 一致性检查;发布前再跑一次(见提交序列)。
