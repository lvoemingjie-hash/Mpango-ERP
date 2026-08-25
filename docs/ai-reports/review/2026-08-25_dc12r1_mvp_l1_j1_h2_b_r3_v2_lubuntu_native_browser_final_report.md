# DC-12R1-MVP-L1-J1-H2-B-R3-V2 — LUBUNTU Native Fresh-Runtime Browser Final

- **日期:** 2026-08-25 (+08:00)
- **执行方:** OpenCode — Lubuntu 原生独立主机
- **产品候选:** 0267ea73（含 R5/R11 401 拦截器修复）
- **冻结 harness:** 8c7e84779cc1810baab32859d3dc353e1028384a（字节不变）
- **模式:** 单次 fresh-runtime 24 节点权威浏览器终验。未合并、未部署、未启动 H2-C。

## 最终裁决

```
STOP_AND_REPORT_CTO
```

23 passed / M1 failed / 0 not-run / 0 skipped / 0 flaky。fail-stop 生效，零重跑。

**M1 失败归因:** 产品端点 `PUT /api/v1/users/{id}/roles` 在 commit 后访问 `user.updated_at` 触发 `MissingGreenlet`（SQLAlchemy async session 过期属性的同步 lazy-load 缺失绿色协程上下文）。预存产品 async 端点缺陷（`users.py:315→55`），0267ea73 的 5 文件 delta 未触碰此路径；非 harness 缺陷、非回归、非环境问题。

**关键正面结果:** R5 和 R11（以及全部 F1-F12 + R1-R12 浏览器旅程节点）**全部通过**，确认0267ea73 的401匿名 reset 拦截器修复有效。F3/F4/F5 B1-R3 规范化中性合同在真实浏览器+真实后端下通过。

## Phase 1 — 证明门（全 PASS）

- `git fetch --all --prune` EXIT 0
- candidate `0267ea73` = remote tip（`zcode/...r3-public-password-recovery-interceptor-closure-2026-08-25`）
- candidate^ == HARNESS `8c7e847`
- delta 恰 5 文件（全部产品路径：authService.ts + 3 frontend tests + ai-ledger）
- harness 零变化（`git diff 8c7e847..0267ea73 -- j1h2b-forgot-reset/` = 0 行）
- 25 文件，porcelain 0

## Phase 2 — 全新独占运行时（PASS）

- 容器 `j1h2b-r3v2-pg16`/`j1h2b-r3v2-redis7`、卷、网络全部新建
- 空库→alembic→037 head
- Backend: uvicorn main:app 127.0.0.1:8000, MPANGO_ENV=staging, 真实 JWT, maildir 镜像
- Frontend: Vite dev host 127.0.0.1:5173（HMR 保留）
- 健康检查: /health 200, /health/ready 200, /health/live 200, frontend 200, proxy 422

## Phase 3 — 供给预检（PASS）

- 6 身份离线验证通过（all_valid=true, special_use_domain_count=0, 5/5 探针拒绝）
- 22 J1H2B_* 变量 bash→node 往返非空

## Phase 4 — 冻结静态门（PASS）

- `--list` 24 tests / 1 spec, CSV 有序
- check-neutrality G1-G6 PASS
- validate-static 7/7 PASS
- tsc --noEmit PASS
- git diff --check PASS
- detect-secrets 0

## Phase 6 — 唯一权威运行

| Node | Status | Time |
|---|---|---|
| F1-D through F2-M (6) | ✓ all passed | 1.1s each |
| F3 (provision A1+X) | ✓ passed | 6.7s |
| **F4 (canonical vs F3)** | **✓ passed** | **1.4s** |
| **F5 (canonical + negative)** | **✓ passed** | **16.3s** |
| R1-R4 | ✓ all passed | ~1s each |
| **R5 (forged token 401)** | **✓ PASSED (1.2s)** | |
| R7-POLICY / R7-POLICY-M | ✓ passed | ~1.2s |
| R8 / R8-M | ✓ passed | ~1.6-3.4s |
| R9 / R10 / R10-M | ✓ passed | ~1.7s |
| **R11 (token replay 401)** | **✓ PASSED (2.1s)** | |
| R12 (leak scan) | ✓ passed | 2.7s |
| **M1 (dual-tenant)** | **✘ FAILED (8.4s)** | |

**R5/R11 首次通过:** 匿名 reset 页面上的401现在留在该页面并显示中性错误面板，零 refresh/logout/navigation。Playwright call log 确认不再导航至 /login。

## Phase 7 — 对账与证据

- 23 passed + M1 failed + 0 not-run + 0 skipped = 24
- F6: maildir 镜像已发送（A1 验证/设置 + F3 忘记链路）
- R6/M2: 引用 BACKEND_ZERO_RED `5570093e`
- R13: 本轮扫描 PASSED（零泄漏发现）
- RT0: BLOCKED_BY_H2_C（PB-1 复核：零 production call sites）
- canonical neutrality: F3/F4/F5 在真实运行时全部通过

## 发布

- 分支: `origin/reports/...b3-v2-lubuntu-native-browser-final-2026-08-25`（父 = `0267ea73`）
- 报告 md + findings csv + evidence 目录 + committed-blob manifest
- local == remote 已验证
