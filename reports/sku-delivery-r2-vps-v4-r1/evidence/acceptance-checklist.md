# 验收清单(冻结于正式运行前)
RUN: SKU-DELIVERY-R2-V4-R1 | AUTH: CTO-AUTH-SKU-DELIVERY-VPS-V1-2026-09-13 | TIER: V4_INDEPENDENT_LINUX_RUNTIME
冻结时间: 2026-09-13T11:46:06+08:00

## 冻结对象
- CANDIDATE: 1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e (分支 codexl/dc-12r1-mvp-l1-sku-delivery-r2-fixture-isolation-2026-09-12)
- TREE: 5712eb85e6bf76d8662a6bb7890e609d09bd7ec0 (已核实匹配)
- PRIOR_BC06: 50f15dedbded1c6d024e322ac84f857699d624e5 (直系祖先已核实)
- worktree: /home/ubuntu/sku-verify/sku-delivery-r2-v4-r1/worktree (status clean)

## 环境冻结
- PG: sku-r2-pg (postgres:15-alpine, 127.0.0.1:15432, 任务角色 sku_task 非超管+CREATEDB)
- Redis: sku-r2-redis (redis:7-alpine, 127.0.0.1:16379)
- venv: pip freeze 89 包 (evidence/pip-freeze.txt, sha256 见 evidence/hashes.txt)
- 关键 env: TEST_DATABASE_URL(.../test_mpango_task), MPANGO_ALLOW_TEMP_DB_CREATE=1, MPANGO_ENV=test, SECRET_KEY=<已生成,存 .env.task>

## Preflight(已于冻结前完成,全 GREEN)
PF-1 角色非超管+CREATEDB ✓ | PF-2 TEST_DB_URL 非空指向任务栈 ✓ | PF-3 临时DB create/connect/drop/absence ✓ | PF-4 alembic 单头 038 ✓

## 正式验收项(顺序执行;预期冻结如下)
- F1 BC-06 聚焦: pytest tests/test_sku_bc06_reprice_guard.py → 预期 37 nodes 全 GREEN
- F2 SKU 回归集: tests/test_sku_m1_catalog_identity.py + test_sku_m1_api_rbac.py + test_sku_b2_catalog_serialization.py + pricing/order/import/intake 回归 → 预期全 GREEN(不设固定数,按实际记录)
- F3 迁移: tests/test_alembic_migrations.py → 记录迁移链(037→038)与全 GREEN
- F4 全量后端套件: pytest tests/ → 预期 3883 collected 全 GREEN(3883 为冻结预期总数)
- F5 变异证伪: backend/tests/sku_b2_serialization_mutations.py 于可丢弃副本执行,每变异须命中业务断言,恢复后复跑 GREEN
- F6 秘密扫描: detect-secrets vs .secrets.baseline(基线 sha256 冻结)

## 规则
- 首个非预期 RED → 保存日志+DB 状态证据 → 停止后续验收(预声明负控/变异预期 RED 除外)
- 运行后不得修改本清单预期
