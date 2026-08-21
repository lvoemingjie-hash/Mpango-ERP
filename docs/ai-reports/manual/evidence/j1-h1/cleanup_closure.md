# Cleanup & Closure — J1-H1（待操作者确认会话结束后执行）

状态：**待执行**（等待操作者确认浏览器会话已结束）

清单（依任务书 Phase 8）：
1. 停止任务后端/前端进程
2. 仅移除任务自有容器/卷/网络（本任务为本地进程 + 任务库，无 Compose 资源）
3. 删除任务 maildir、密钥、浏览器配置与临时 worktree
4. 核验任务端口（8000/5173/29432）已释放
5. 核验宿主自有容器与 git refs 未变化

注意：交付物（docs/ai-reports/manual/**）须在清理前提交至报告分支
`reports/dc12r1-mvp-l1-j1-h1-desktop-human-journey-2026-08-21` 并 push（STOP after push）。
