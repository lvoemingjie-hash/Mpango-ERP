# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R1-V1 — LUBUNTU Native Independent Harness Authenticity Review (Kilo-Parallel)

- **日期:** 2026-08-24（+08:00）
- **执行方:** OpenCode — 原生 Lubuntu 独立运行时审查（非 WSL；与 Kilo 平行的独立审查，报告/分支均以 **LUBUNTU** 标识避免冲突）
- **模式:** 对冻结 Playwright harness 的独立、有界、对抗性源码与真实性审查。未修改候选、未启动任何产品运行时（backend/frontend/PostgreSQL/Redis 全程零启动）、未执行任何权威浏览器旅程、未合并、未部署。

## 最终裁决

```
STOP_AND_REPORT_CTO
```

唯一缺陷（P2，harness 本地、可修复）：**R12 沉降条件依赖 Vite/HMR 宿主形态**——`waitForLoadState('networkidle', 15s)` 在 Vite dev server 下被 @vite/client 常开 HMR WebSocket 永久阻断，15s 超时必红；配合 `maxFailures:1` 将使未来单次权威浏览器运行在 dev 宿主下确定性假红中止。其余全部审查轴 PASS。按指令"若会被持续连接或后台请求阻断，判为缺陷"，判为缺陷并 STOP 上报。

## Phase 1 — 证明与范围（PASS）

| 检查 | 结果 |
|---|---|
| `git fetch --all --prune` | EXIT 0 |
| candidate `e65e9a7f61c78906c2c5874d6589d4bada23942c` == 远端 `origin/zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r1-global-serial-fail-stop-2026-08-24` 尖端 | PASS |
| `candidate^ == d123e96da08f10a1976ce2a75d7392039eec0a44`；`d123e96d^ == 8c462170804322d3f73803d8991c00879582e232` | PASS |
| 产品候选 `8c462170` / 协议 `132cf7ed` / 后端 Kilo `4d42ffca` / Lubuntu 双栈零红 `5570093e` / 受保护基线 `6e9470a1` 引用在位 | PASS |
| detached 隔离 worktree（`/home/ivy/MPANGO/dc12r1-b1r1-harness-wt`）porcelain 0 行 | PASS |

### 范围对账披露（26 → 21，非缺陷）

指令冻结"累计 `8c462170..e65e9a7f` 恰好 26 个新增文件"。实测 git 真值：**21 个新增文件**，全部位于 `j1h2b-forgot-reset/`，产品/测试/migration/模型/依赖/前端 package-lockfile/部署文件零变化（name-status 仅 A）。对账：B1（d123e96d）新增恰 26 文件；R1（candidate）按其提交信息执行 P1 修复——删除 6 个分片 spec、新增 1 个统一 spec、修改 5 个文件 → 26 − 6 + 1 = **21**。该合并是指令自身 Phase 2（"唯一 spec 为 tests/forgot-reset.spec.ts"、"单一外层 serial describe 包裹全部 24 节点"）的结构性前提：B1 的 6 分片形态不可能满足 Phase 2。候选对其自身范围如实陈述（R1 提交信息逐条披露），故记为**指令冻结数字滞后于 R1 授权合并的披露项**，不计缺陷。

## Phase 2 — Inventory 与 Fail-Stop（PASS）

| 检查 | 结果 |
|---|---|
| protocol CSV committed blob 与 `132cf7ed` 字节一致 | PASS — 两处 blob 同为 `29a2bdd30b8ffd9142404dd530486d7fa6fd1f15` |
| CSV 严格 29 数据行 × 15 列 | PASS（csv.DictReader 复核；表头 15 列名逐一相符） |
| browser 24 / non-browser 5 | PASS（24 = 22 BROWSER + BROWSER+POSTCOND + BROWSER_WITH_OFFICIAL_API_PRECONDITION；5 = F6/R6/M2/R13/RT0） |
| `--list` 精确 24 且标题+顺序与 inventory browser 行完全一致 | PASS（有序相等，validator 第 [3] 步主动强制；实测 ordered_equal=True） |
| 唯一 spec `tests/forgot-reset.spec.ts` | PASS（tests/ 目录仅此一个 .spec.ts；validator 强制） |
| 单一外层 serial describe 真实包裹全部 24 节点 | PASS（spec L84-85：一个 describe + `test.describe.configure({ mode: 'serial' })`；24 个 test 注册序 == CSV 行序） |
| fullyParallel:false、workers:1、retries:0、maxFailures:1 | PASS（playwright.config.ts；comment-stripped 强制检查） |
| F6/R6/M2/R13/RT0 不出现在 browser PASS | PASS——五者非 Playwright 节点（registry + validator 双证），永不计入浏览器结果 |
| RT0 保持 BLOCKED_BY_H2_C、无 API 绕过 | PASS（node-registry.json status=BLOCKED_BY_H2_C；reconciliation.ts 不变量强制；无零售商 API 桥接代码存在） |

## Phase 3 — State 与 Timing 真实性

| 检查 | 结果 |
|---|---|
| token/state 仅单一 serial spec 同 worker 内存传递 | PASS —— 全链路经 `src/token-store.ts` 进程内状态（resetLink/usedResetLink/fingerprints/provisioning handles）；workers=1 + 单文件 serial 保证单进程单线程顺序；零磁盘/零日志/零跨文件缓存；无文件名排序依赖（唯一 spec） |
| 首个失败后不制造级联红节点 | PASS —— `maxFailures:1` 使首个失败即中止整趟（serial 模式余下节点不再执行，无级联红）；validator comment-stripped 强制该行在位 |
| R2 等待真实 URL/hash 清洗条件 | PASS —— `waitForFunction(hash === '' && pathname === '/reset-password', 15s)` 为真实 replaceState 效果条件，非宿主假设 |
| **R12 settle 条件** | **FAIL → 缺陷 F1（见下）** |
| 无 waitForTimeout/sleep/重试/条件通过 | PASS —— validator 对 tests/+src+config 做 `waitForTimeout` 标记扫描（含注释文本）；全仓 grep 零命中；retries:0；无 skip/fixme/only/条件通过路径 |

### 缺陷 F1（P2）— R12 networkidle 沉降条件为 Vite/HMR 宿主相关假设

- **位置:** `j1h2b-forgot-reset/tests/forgot-reset.spec.ts:488`
  `await page.waitForLoadState('networkidle', { timeout: 15_000 });`
- **机制:** Vite dev server 向每个页面注入 `@vite/client`，其 HMR WebSocket 于页面加载即常开；Playwright 官方文档明确 networkidle 在 WebSocket/HMR 应用下不可达（ discouraged ）。协议 §5.2 冻结的目标运行方式为"前端独立回环端口经 vite 代理"（vite.config.ts server.port 5173 + server.proxy['/api']→8000；env.ts 注释亦称 "task loopback vite origin"）——该措辞的自然实现是 vite dev 宿主 ⇒ R12 必然 15s 超时假红 ⇒ fail-stop 中止整个权威运行。
- **反证面:** 产品前端本身零持续连接——frontend/src 无 WebSocket/EventSource/SSE/setInterval/serviceWorker 命中；ResetPasswordPage 的 useEffect 仅本地 URL 清洗无网络调用。故若 launcher 改用生产构建静态服务/vite preview，networkidle 可靠沉降（~500ms）。**即：R12 成败取决于未被任何冻结文档固定的 dev-vs-build 宿主选择**，正是指令禁止的 "Vite/HMR 宿主相关假设"。
- **分类:** `HARNESS_SETTLE_CONDITION_HOST_MODE_DEPENDENT__NETWORKIDLE_BLOCKED_BY_VITE_HMR_WEBSOCKET_UNDER_PROTOCOL_VITE_PROXIED_RUNTIME`（in-scope：该 networkidle 为 B1-R1 替换 waitForTimeout(500) 时引入）
- **影响:** P2 —— 阻断未来单次权威浏览器运行的确定性假红（dev 宿主下）；非产品缺陷；修复为 harness 本地改动（有界应用条件等待替代 networkidle，或冻结 preview/build 服务契约）。
- **建议修复方向（供 CTO 裁决，不在本轮实施）:** 以有界真实条件替代——如 `expectResetFormRendered` 后追加 `waitForFunction` 断言 reset 表单就绪 + console 观察窗口闭合的固定短窗（如再等一次 bounded 条件而非网络静默），或在协议 §5.2 显式冻结 `vite preview`/生产构建服务为唯一授权宿主后保留现状。

## Phase 4 — Journey 真实性（PASS，除 R12 settle 归入 F1）

逐节点核验（对照冻结于 8c462170 的产品锚点，UI_COPY 全部字符串与 LoginPage/ForgotPasswordPage/ResetPasswordPage/WorkspaceSelectorPage 源码逐一比对命中）：

- F1-D/T/M、F2-D/T/M：真实 `/login` 入口 → `getByRole('link', {name:'Forgot password?'})` 真实点击 → 真实表单结构断言（#email、按钮、"恰好一个 input"）；F2-M 附加 scrollWidth≤390 无横向溢出。**真实 UI**。
- F3/F4/F5：经 UI 提交（#email fill + 按钮点击）；中性比较仅保留 status/sha256(body)/bodyLengthBytes 三元组指纹 + 可见文案精确比较，原始响应体即刻出丢弃；F5 另有 maildir 负窗口 15s 只读零邮件后置。**无 helper 返回值或硬编码布尔冒充 UI 成功**。
- R1/R2：maildir 链接（F6 面）→ 浏览器打开；R1 断言页面 GET 零 API 调用、请求 URL 零 token 泄漏、落定 URL==`/reset-password`、hash 空；R2 等待真实清洗条件（见上）。fragment-only 与清洗真实执行。
- R3：query-token 构造访问 → Invalid Link 面板可见 + `/api/v1/auth/reset-password` 调用数 **0** + URL 清洗。
- R4/R5：缺 token 提交零 reset API 调用；伪造 token 经真实 UI 提交 → 真实响应 waitForResponse 断言 401 + 中性错误文案精确匹配。
- R7-POLICY/-M：两视口（1280x800/390x844）弱密码（7 字符合成值）经真实 UI 被 zod 文案拦截且零 API。
- R8/R8-M：均为完整 UI reset（打开链接→填新密码→提交→200→成功面板）；R8-M 为独立新一轮 forgot→maildir→reset 循环（同 P2 值），**不复用虚假成功状态**。
- R9/R10/R10-M/R11：真实登录页验证旧密码 401 拒绝、新密码接受（waitForURL '/'）、已用链接重放 401 且重放后 P2 仍可登录。
- R12：四表面扫描（URL/storage/console/network metadata）+ 秘密子串匹配；失败输出仅 surface:field 对，**不含秘密值**（除 F1 所涉 settle 行外全部成立）。
- M1：两个独立 `browser.newContext()` 分别验证双租户旧拒/新受/工作区选择器精确含 W1+W2。

## Phase 5 — Provisioning 边界（PASS）

- M1 前置严格正式 API：W1/W2 owner 经官方 signup→verify-email→setup-credential→login→select-tenant 全生命周期（不同邮箱由 env distinctness 强制 fail-closed）；M 在两租户各经正式 `POST /api/v1/users` 创建——同一规范化邮箱（env 层 lowercase 归一）、**同一 P1**（两次调用均传 `env.m1.m.initialPassword`）；双侧正式 admin role（GET /roles 定位 'admin' + PUT /users/{id}/roles + 响应复核）；前置门禁=M 登录 available_tenants 排序后**精确等于** {W1,W2}。
- X（不合格邮箱）经官方 create + 官方 soft-delete 构造。
- forgot/reset 动作全程零 fetch/API helper 绕过（spec 内 journey 动作仅出自 ui-journey.ts 的 UI helpers；api-client.ts 仅供给前置 + 协议允许只读后置如 GET /roles）。
- 无 SQL、无 ORM、无手写 hash、无 debug endpoint、无数据库修补（全源码核验）。

## Phase 6 — Secret 与证据边界（PASS）

- 凭据全部来自 `J1H2B_*` 环境变量，缺失/空值/格式错 fail-closed，错误仅报变量名（env.ts requireAll/normalizeOrigin/requireEmail/requirePassword/assertDistinct）。
- maildir token/link 仅存在于内存（fs 只读提取，从不写盘/日志/截图）。
- trace/screenshot/video 配置 'off'（config 不变量强制）。
- JSON/JUnit/list/错误消息输出纪律：assertSan 全部 field-only 文案（URL/响应体/存储/密码/token 类断言一律不用裸 expect）；leak-scan findings 仅 surface:field；R12 失败消息标注 "(values withheld)"；apiFetch 错误仅 endpoint 名+status+code。核验所有失败消息模板均无值插值。
- artifact scanner（tools/scan-artifacts.mjs）覆盖 R13 全部预期产物：machine JSON/JUnit/CSV/日志的模式扫描 + `--secrets-from-env` 运行时秘密字节匹配 + 截图/视频/trace 文件类型封禁（.png/.jpg/.jpeg/.webp/.zip/.webm/.mp4/.trace）。

## Phase 7 — 独立突变门（全部 RED → 字节还原 → GREEN）

在 detached worktree 内独立执行并恢复：

| 突变 | 结果 |
|---|---|
| 删除 `maxFailures:1` | **RED**（missing frozen invariant maxFailures: 1）→ 还原 GREEN |
| 删除 serial mode 声明 | **RED**（must declare test.describe.configure）→ 还原 GREEN |
| 新增第二个 spec | **RED**（must contain exactly one spec file）→ 还原 GREEN |
| 交换 F1-T/F1-M 两节点注册序 | **RED**（listed order diverges at position 2；--list 仍 24 但有序相等破坏）→ 还原 GREEN |
| 重新加入 waitForTimeout | **RED**（forbidden marker waitForTimeout found in src/ui-journey.ts）→ 还原 GREEN |

还原后：worktree porcelain **0** 行、HEAD == `e65e9a7f`、`git diff HEAD` 空——candidate tracked bytes 与原 SHA 一致；`--list`（Total: 24 tests in 1 file）与 validate-static.mjs（STATIC GATE PASSED 5/5）重新 **GREEN**。

## Phase 8 — Reviewer Runtime（仅限清单内，全部 PASS；零产品运行时启动）

| 门 | 结果 |
|---|---|
| `pnpm install --frozen-lockfile` | PASS（12.2s，lockfile 零漂移；@playwright/test 1.49.1 exact-pin） |
| Playwright `--list` | PASS — Total: 24 tests in 1 file，标题+顺序与 CSV browser 行有序相等 |
| `node tools/validate-static.mjs` | PASS — 5/5 STATIC GATE PASSED |
| `npx tsc --noEmit` | PASS（exit 0） |
| 突变门 ×5 | 见 Phase 7 |
| `git diff --check e65e9a7f~1..e65e9a7f` | PASS（clean） |
| detect-secrets（tests/src/tools/config/inventory/docs） | PASS — 0 findings |
| UTF-8 strict / no-BOM / no-CR | PASS — 21 个 harness 文件零违例 |
| GitNexus analyze/status | PASS — analyze 34,258 nodes / 56,574 edges / 743 clusters / 300 flows；status：索引提交 `e65e9a7` == 当前提交，✅ 已是最新 |
| 产品 runtime 启动 | **未发生**（backend/frontend/PG/Redis 全程未启动；未执行任何旅程测试） |

## 附注

- 本轮为 LUBUNTU 原生环境独立审查（非 WSL）；GitNexus 经任务自有全新安装执行（本机既有安装符号链接损坏，已披露）。
- 未修改候选任何字节；未触碰受保护 refs；未产生任何需要清理的产品容器/卷/端口。
- 下一步（CTO 裁决后）：修复 F1 或冻结宿主契约 → 独立 fresh-runtime 单次权威浏览器执行。
