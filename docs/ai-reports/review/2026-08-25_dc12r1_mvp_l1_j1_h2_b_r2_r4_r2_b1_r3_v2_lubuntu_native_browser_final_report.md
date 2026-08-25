# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3-V2 — LUBUNTU Native Single Fresh-Runtime Authoritative Browser Final

- **日期:** 2026-08-25（+08:00）
- **执行方:** OpenCode — Lubuntu 原生独立主机（非 WSL）
- **模式:** 单次 fresh-runtime 24 节点权威浏览器终验。未合并、未部署、未启动 H2-C。

## 最终裁决

```
STOP_AND_REPORT_CTO
```

单一首红（fail-stop 生效，零重跑）：**R5**。13 passed / 1 failed (R5) / 10 did-not-run / 0 skipped / 0 flaky。
分类：`PRODUCT_401_SESSION_INTERCEPTOR_LOGOUT_REDIRECT_ON_ANONYMOUS_RESET_PAGE__NEUTRAL_ERROR_SURFACE_NEVER_RENDERS`（产品侧行为与冻结协议 expected_ui 冲突；非 harness 缺陷、非环境缺陷）。

## Kilo 状态声明

```
KILO_HARNESS_VERDICT_ACCEPTED_BUT_REPORT_PUBLICATION_PENDING
```

Kilo 已对 HARNESS `8c7e84779cc1810baab32859d3dc353e1028384a` 给出明确 PASS verdict，但其报告分支截至本发布时尚未推送/不可见。本报告不虚构任何 Kilo report SHA，仅记录该状态标记。

## Phase 1 — 证明门（全 PASS）

`git fetch --all --prune` EXIT 0；HARNESS `8c7e847` == 远端源分支 tip；detached worktree 精确位于 HARNESS 且 porcelain 0；相对 PRODUCT_SOURCE `8c462170` 产品路径 diff 为 0；harness 恰 25 文件；V2 STOP `3fb185be` / V3 STOP `888fd207` / LUBUNTU_HARNESS_REVIEW `67981ccf` / BACKEND_ZERO_RED `5570093e` / product-dev-recovered `6e9470a1` 全部未漂移。

## Phase 2 — 全新独占运行时（全 PASS；零 V2/V3 复用）

- 容器 `j1h2b-v4-pg16`（postgres:16-alpine，仅 127.0.0.1:55441）、`j1h2b-v4-redis7`（redis:7-alpine，仅 127.0.0.1:56381）；卷 `j1h2b-v4-{pgdata,redisdata}`；网络 `j1h2b-v4-net`——全部新建，创建前 j1h2b docker 残留为 0。
- 空库 `mpango_erp`（0 表）→ `alembic upgrade head` → 唯一 head `037_payment_declarations_schema`。
- Backend：生产入口 `backend/main.py`（main:app）经任务私有 launcher 于 uvicorn 127.0.0.1:8000；`MPANGO_ENV=staging`；真实 JWT（全新 64 字符 SECRET_KEY，值不记录）；全新 REPORTING_USER_PASSWORD；launcher 按 harness README 的 launcher duty 将非生产邮件 sink 进程内镜像至全新 maildir（无新增 HTTP 面、无 SQL/ORM）；`PUBLIC_FRONTEND_URL=http://127.0.0.1:5173`。
- Frontend：**Vite dev host** `http://127.0.0.1:5173`（HMR WebSocket 运行期保留）；`/api` 代理经登录探针验证（→422 后端校验）。
- 健康：/health、/health/ready、/health/live 全 200；frontend 200。
- 全新 maildir（起始 0 文件）、全新身份与凭据；V2/V3 数据、身份、容器、maildir、token 零复用。

## Phase 3 — 任务供给预检（全 PASS）

- 身份域：非 special-use 真实 TLD 子域 `mail.j1h2b-v4-task.dev`（完整邮箱不入任何记录）。
- 用候选 backend 实际安装的 pydantic SignupRequest（EmailStr）离线验证：`validated_email_count=6`、`all_valid=true`、`special_use_domain_count=0`（5 个 .invalid/.test/.local/localhost 探针全部被正确拒绝——V2 根因类别在本域下不复现）；owner signup 完整 payload 接受。
- 22 个 J1H2B_* 变量经 bash-source → node 往返证明非空（只记变量名+布尔值；TOTAL=22 MISSING=0；MAILDIR_ROOT_READABLE=true）。env 文件全值加引号（无未引用空格）。
- 任一失败即须在 Playwright 前 STOP——未触发。

## Phase 4 — 冻结静态门（全 PASS）

| 门 | 结果 |
|---|---|
| `pnpm install --frozen-lockfile` | PASS |
| `pnpm exec playwright test --list` | PASS — 24 tests / 1 spec，顺序与 CSV browser 行一致 |
| `node tools/check-neutrality.mjs` | PASS — G1–G6 |
| `node tools/validate-static.mjs` | PASS — 7/7 |
| `pnpm exec tsc --noEmit` | PASS |
| workers=1、retries=0、maxFailures=1 | 保持（validator 强制） |
| 24 browser + 5 non-browser = 29 | PASS |
| 25/25 strict UTF-8、无 BOM、无 CR（LF-only） | PASS |
| git diff --check / scoped detect-secrets | PASS / 0 findings |

Playwright 浏览器 chromium v1148 + headless shell 本轮新装至宿主级缓存（基础设施准备）。

## Phase 5 — 正式供给边界（PASS）

F3 内 A1 经官方 signup → maildir verify-email → setup-credential → login → select-tenant 全生命周期供给；X 经官方 POST /api/v1/users + 官方软删除构造。全程零 SQL/ORM/手写哈希/debug endpoint/数据库修补；forgot/reset 动作全部经渲染 UI。

## Phase 6 — 唯一权威运行（单次；fail-stop 生效）

命令恰一次：`pnpm exec playwright test`（workers=1 来自冻结配置；无 grep/shard/retry/repeat-each/重跑/数据修复）。启动 UTC+8 10:08:27，历时 53.9s 至 fail-stop：

| F1-D | F1-T | F1-M | F2-D | F2-T | F2-M | F3 | F4 | F5 | R1 | R2 | R3 | R4 | **R5** | R7×2 | R8 | R8-M | R9 | R10×2 | R11 | R12 | M1 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **✘** | — 未运行（fail-stop） |

- **F3/F4/F5 在 B1-R3 canonical neutrality 合同下全部通过**（timestamp 值豁免的语义规范化对比在真实浏览器+真实后端下成立——V3 的 raw-body 结构性不可满足问题正式闭环于运行时证据）。
- **R5 失败精确归因**：伪造 token 提交确实触达真实 API 且 `assertSan(status===401)` 先行通过（后端行为符合协议预期 401）；随后等待固定中性错误文案时 Playwright call log 记录页面被导航至 `http://127.0.0.1:5173/login`。机制链（frontend/src/services/api.ts 响应拦截器）：`/auth/reset-password` 不在 `skipAuthInterceptors` 豁免集（仅 refresh/login/client-login 豁免）→ 匿名 reset 页收到真实 401 → 无 refreshToken → `logout()` + `window.location.href='/login'` → ResetPasswordPage 卸载，中性错误面板永不进入 DOM。
- 分类：**PRODUCT_401_SESSION_INTERCEPTOR_LOGOUT_REDIRECT_ON_ANONYMOUS_RESET_PAGE__NEUTRAL_ERROR_SURFACE_NEVER_RENDERS**。范围：产品侧与冻结协议 expected_ui 的冲突（同一机制必然影响 R11 重放节点）；排除 harness 缺陷与环境缺陷（13 个先行节点含全部供给链、canonical 对比、fragment 清洗均绿）。新颖性：V2 止于启动前、V3 止于 F4——R5 属历史上首次真正执行到位。
- 首红即停：maxFailures=1 生效，"Testing stopped early after 1 maximum allowed failures"；未重跑刷绿。

## Phase 7 — 对账与证据（已提交本分支 evidence 目录）

authoritative results.json/JUnit、24 行节点 CSV、test_list、reconciliation.json（29 节点 gap=0：browser 24 = 13 passed + 1 failed + 10 not-run；F6 按 launcher maildir 链路记账本轮实际镜像 3 封；R6/M2 引 BACKEND_ZERO_RED `5570093e` 前置证据；R13 本轮扫描 PASSED 零泄漏发现；RT0 继续 BLOCKED_BY_H2_C 不计 PASS——PB-1 复核 retailerForgotPassword 零调用点）、failure_set.json、runtime/provisioning preflight、canonical-neutrality 结果（G1–G6 + F3/F4/F5 运行时通过）、cleanup closure、committed-blob manifest。证据不含密码、邮箱全文、JWT、Authorization、SECRET_KEY、邮件 token、maildir 原文、env 文件、trace/截图/视频。

## Phase 8 — 清理（cleanup.md）

backend/vite 进程终止、容器/卷/网络删除、四端口（8000/5173/55441/56381）释放证明、凭据 shred、maildir 与任务目录销毁、review worktree 移除；冻结 refs 复验不变。

## 裁决链

本 STOP 将 R5/R11 的产品拦截器冲突交由 CTO 裁决（可选方向：产品为匿名 reset 路径加入 skipAuthInterceptors 豁免或等价处理——属产品候选变更，须走新一轮候选流程；harness 无需变更）。在 CTO 裁决前不得进行任何权威重跑。
