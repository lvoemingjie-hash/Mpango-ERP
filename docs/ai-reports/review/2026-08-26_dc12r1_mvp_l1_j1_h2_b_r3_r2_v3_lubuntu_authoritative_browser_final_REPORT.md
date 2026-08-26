# DC-12R1-MVP-L1-J1-H2-B-R3-R2-V3 — LUBUNTU Native Single Fresh-Runtime 24-Node Authoritative Browser Final

- **日期:** 2026-08-26（+08:00）
- **执行方:** OpenCode — Lubuntu 原生独立主机
- **产品候选:** `25626f4d`（0267ea73 拦截器修复 + crud/user.py MissingGreenlet 修复 + R3-R2 残留闭合）
- **冻结 harness:** `8c7e847`（candidate 内字节不变，diff=0）
- **CLAIM_CEILING:** INDEPENDENT_BROWSER_GATE_PASS（非 merge/deployment approval）
- **模式:** 单次 fresh-runtime 权威浏览器终验。未合并、未部署、未启动 H2-C。

## 最终裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R3_R2_V3_LUBUNTU_AUTHORITATIVE_BROWSER_FINAL
```

**24/24 browser nodes passed** — failed=0, skipped=0, flaky=0, not-run=0。单次调用（17:12:33 启动，1.3m），fail-stop 未触发。

## Phase 1 — 证明门（全 PASS）

candidate == 远端 tip；BACKEND_AUTHORITY `90f96e3f` 父 == candidate 且远端未漂移；j1h2b-forgot-reset/** 在 HARNESS_FREEZE `8c7e847`..candidate 零差异（25 文件）；detached clean checkout porcelain 0；protected/Kilo/历史 STOP refs（含 PRIOR_BROWSER_STOP `9d6b3e43`）全部未变。运行前/中/后 candidate tracked bytes 一致（porcelain 全程 0）。

## Phase 2 — Fresh Runtime（PASS）

新容器 r3r2v3-pg（PG16-alpine @127.0.0.1:15604，max_connections=300）/r3r2v3-redis（@16604）、卷/网络全新；空库→Alembic 37 迁移→唯一 head 037（tenant_registrations 表在场实证）；backend 生产入口 main:app（uvicorn 127.0.0.1:8000，MPANGO_ENV=staging、真实 JWT、任务私有 SECRET_KEY）；frontend=candidate 源码 Vite dev host（--host 127.0.0.1 --strictPort，HMR 保留）；PUBLIC_FRONTEND_URL 精确等于 J1H2B_BASE_URL；任务私有 maildir 起始 0 文件；四端口独占且创建前无监听；零历史复用；全程零 SQL/ORM 直接置备/手写哈希/数据库修补。

## Phase 3 — Environment Preflight（PASS）

browser_preflight.json：22 个 J1H2B_* 变量 present/nonempty 全 true（仅名+布尔）；密码长度+互异合同满足；6 身份邮箱唯一；域 mail.j1h2b-v4-task.dev 非 special-use；候选实际 SignupRequest/EmailStr 离线验证 all_valid=true、5/5 special-use 探针拒绝；origins 一致；chromium 可用；trace/screenshot/video off。
VOID 披露：attempt #1 为 VOID_ENVIRONMENT_PRECHECK——首次 runtime 构建时 alembic 因 venv 未就绪而从未应用（executor 设置遗漏，预检当时缺迁移项），F3 即红后按指令终止归档（void_attempts/），栈销毁重建并补验证（37 迁移+表在场）后才启动 THE 唯一权威调用。

## Phase 4 — Static Pre-Gates（PASS）

--list 24 nodes / 1 spec / inventory 有序一致；check-neutrality G1–G6 全绿；validate-static 7/7；tsc --noEmit 干净；workers=1/retries=0/maxFailures=1/serial；无 only/skip/fixme；无 waitForTimeout/networkidle/fixed sleep；24+5=29 gap=0；RT0 BLOCKED_BY_H2_C 无 API 绕过。静态门后未修改 harness/产品/环境语义。

## Phase 5 — Single Authoritative Browser Run

仅调用一次 `pnpm exec playwright test`（workers=1 来自冻结配置）。**24 passed (1.3m)**：

| 合同 | 结果 |
|---|---|
| 24/24 nodes | ✓（node_results.csv 逐行） |
| F3/F4/F5 canonical neutrality | ✓ |
| R5 匿名401留 reset 页+中性错误+零导航 | ✓（1.2s） |
| R11 重放401+P2 复验 | ✓（2.4s） |
| M1 POST users + PUT roles 成功；共享身份精确 W1/W2；P1 双拒 P2 双受 | ✓（21.5s）——crud/user.py MissingGreenlet 修复在真实异步端点生效 |
| R12 五面泄漏扫描 | ✓ |

视口披露：390px 为桌面引擎模拟视口，仅报 viewport result。

## Phase 6 — Non-Browser Accounting（29 节点 gap=0）

24 browser PASS；F6 maildir precondition PASS（本轮镜像 10 封供给/重置邮件，harness 内存读取）；R6/M2 = BACKEND_PRE_GATE_ACCEPTED 引用 `90f96e3f`；R13 artifact scan PASS（3 文件 --secrets-from-env 零泄漏）；**RT0 = BLOCKED_BY_H2_C（不计 PASS）**。

## Phase 7 — Evidence & Secret Boundary

evidence 目录含指令要求的全部 12 项（REPORT.md/browser_preflight.json/test_list_24.txt/authoritative_playwright.json/authoritative_junit.xml/node_results.csv/reconciliation.json/failure_set.json[空]/non_browser_accounting.json/artifact_scan.json/cleanup_closure.md/committed-blob manifest）。console/junit 扫描确认零 SECRET_KEY/口令/JWT/Bearer/token；maildir 原文与 env 文件未入库；manifest detached recompute 0 mismatch。

## Phase 8 — Cleanup（cleanup_closure.md）

backend/frontend 终止；PG/Redis 容器/卷/网络删除；maildir/私有 env/浏览器状态/运行目录/worktree 销毁；四端口释放证明；宿主资源与冻结 refs 不变。

## 裁决链

本 PASS 完成链路：BACKEND_AUTHORITY `90f96e3f`（R1 后端门）→ 本轮 BROWSER GATE。CLAIM_CEILING 为 INDEPENDENT_BROWSER_GATE_PASS——merge review 与 deployment approval 不在范围内。即使 PASS 也 STOP。
