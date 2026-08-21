# Runtime Preflight — DC-12R1-MVP-L1-J1-H1

时间：2026-08-21 14:20 (+08:00)
执行者：ZCode（接手 OpenCode 的环境核验，OpenCode 负责环境搭建）

## 冻结版本核验

- worktree HEAD：`c5b66d26b83a0cc6170282de1e2fe281e448b2a8`
- 任务书冻结 SHA：`c5b66d26b83a0cc6170282de1e2fe281e448b2a8` ✅ 一致
- `git status`：干净（无产品/源码/测试改动）

## 运行时状态

| 项目 | 结果 |
|---|---|
| 后端 http://127.0.0.1:8000/health | 200 `{"status":"healthy",...}` |
| /health/live | 200 |
| /health/ready | 200 |
| 前端 http://127.0.0.1:5173/ | 200 |
| MPANGO_ENV | staging（真实 JWT 认证） |
| Alembic head | `037_payment_declarations_schema` ✅ 与任务书要求的 head 037 一致 |
| maildir | `C:\Users\Jeff0\dc12r1_j1h1_runtime\maildir\`（空，就绪） |

## 与任务书的偏差（记录，不阻断）

1. 任务书 Phase 2 要求"task-owned Compose project + 全新 PG16/Redis7 卷"；
   OpenCode 实际采用本地 venv + `run_backend.py`（同进程 mailbox dump 线程）方案。
   前一任务 J1-R0 已采用相同方案并被接受，故按 ENVIRONMENT_ONLY 记录。
2. 后端经 launcher 直接运行 uvicorn（production entrypoint main:app），符合
   "Start backend through production entrypoint" 要求。

## 就绪判定

环境就绪，可进入 Phase 3/4（人工演练）。
