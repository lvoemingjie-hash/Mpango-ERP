# DC-12R1-MVP-L1-J1-H2-B-R3 — 公共密码恢复拦截器收口（Public Password-Recovery Interceptor Closure）

- 日期：2026-08-25（+08:00）；执行者：ZCode（OpenCode 会话）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r3-public-password-recovery-interceptor-closure-2026-08-25`
  （自父提交 `8c7e84779cc1810baab32859d3dc353e1028384a` = B1-R3 冻结点创建）
- 冻结引用（fetch --all --prune 后核实）：
  - 父提交 `8c7e8477…`；Lubuntu STOP `f7dd9aa3331217af2f5cab68dad7aa533093401f`；
    Kilo truth closure `6785f40ae2bca42cbfd099616d29b0537a3a59c1`；
    V2 STOP `3fb185be…`；V3 STOP `888fd207…`（全部原样保留）
- 裁决：`STOP_AND_REPORT_CTO_AWAITING_KILO_H2_B_R3_SOURCE_REVIEW`

## 1. 根因合同确认（实现前）

1. ResetPasswordPage 正确捕获 401 并准备固定中性文案（页面代码复核属实）。
2. api.ts 对 `skipAuthInterceptors=true` 已有公共旁路（response 拦截器
   L119-121：直接 reject；不触 toast/refresh/queue/logout）。
3. authService 四个公共恢复调用未设旁路（复核属实：forgotPassword /
   resetPassword / retailerForgotPassword / retailerResetPassword 均裸
   api.post）。
4. 匿名 401 因此落入 refresh/logout 路径并强制 `window.location.href='/login'`。
5. 修复位于调用方配置；未引入任何 URL 白名单（api.ts 零改动）。

## 2. GitNexus impact（编辑前门禁）

- 本任务 worktree 重建索引：`npx gitnexus analyze`（28,750 节点 /
  60,026 边 / 300 flows）。
- `impact authService.ts --direction upstream --depth 3`：
  **MEDIUM**（impacted 12；direct 10 —— 10 个页面文件 IMPORTS，d2
  AppRouter，d3 App；affected_processes 0）。未达 HIGH/CRITICAL → 按
  门禁继续。导出签名未变（仅在实现内部加 per-call config），10 个直接
  导入方源兼容。

## 3. 产品改动（恰 1 个产品文件）

`frontend/src/services/authService.ts`：四个公共恢复调用统一加
`{ headers: { Authorization: '' }, skipAuthInterceptors: true }`：

- 空头显式存在 → PW1-R2-R2 大小写不敏感优先级保证 stale store token
  不注入；
- skip → 401 原样 reject 给页面（零 refresh/queue/logout/toast/导航）；
- 200 成功路径不变；不触 signup/login/setup/verify 等其他流程。

api.ts / backend / Harness / migration / 依赖 / lockfile **零改动**。

## 4. 测试范围（恰 5 文件 delta）

1. `frontend/src/services/authService.ts`（产品修复）
2. `frontend/src/tests/PublicPasswordRecoveryInterceptor.test.tsx`（新增，
   有界真实拦截器测试：真实 api 实例 + 录制 adapter + 真实页面，
   authService 不 mock；T1–T6 覆盖任务真实性 10 项）
3. `frontend/src/tests/CredentialLifecyclePages.test.tsx`（最小更新：
   forgot/reset 两处断言补第三参 objectContaining 旁路配置）
4. `frontend/src/tests/RetailerCredentialPages.test.tsx`（最小更新：
   retailer reset 断言补第三参）
5. 本台账

真实性测试映射：T1=①②③（批发商 401 停留 + 中性面板 + 零
refresh/logout/导航/toast + 会话不动）；T2=⑦（200 成功面板）；T3=④
（零售商 401 停留 /retailer/reset-password + 中性面板）；T4=⑤⑥（stale
contextual session 下四调用显式空 Authorization + 401 原样 reject +
状态不改写）；T5=⑧（普通受保护 401 仍走 refresh/重试旧合同——注意
refresh 经全局 axios 带 baseURL 前缀 `/api/v1/auth/refresh`）；T6=⑨
（URL/日志/渲染面零 token/password/Authorization 泄漏）；⑩（真实
api.ts 拦截器与真实页面，authService 不 mock）为文件结构本身保证。

开发期自纠（如实记录）：首版 neutral401 handler 为箭头 return 错误
对象（adapter 误当成功响应 resolve）与 T5 refresh key 未带 baseURL
前缀 —— 均以最小诊断定位后修复；T5 断言 key 同步修正。

## 5. 变异真值门 M1–M5（全部先 RED 后恢复 GREEN）

| 门 | 变异（临时，均已字节级恢复） | RED | 恢复 |
|---|---|---|---|
| M1 | resetPassword 删 skipAuthInterceptors | 2 failed（T1/T4） | 6/6 GREEN |
| M2 | 四调用删显式空 Authorization | 1 failed（T4 stale 边界） | 6/6 GREEN |
| M3 | retailerResetPassword 删 skip | 2 failed（T3/T4） | 6/6 GREEN |
| M4 | api.ts 删 skip 旁路（skip 请求重回全局 401 路径） | 3 failed | 6/6 GREEN |
| M5 | ResetPasswordPage 弱化中性文案（透传后端 message）+ 强制导航 /login | 2 failed | 6/6 GREEN |

恢复后三个变异目标文件 SHA-256 与快照逐一相同（mutation-snapshots.txt；
api.ts/ResetPasswordPage.tsx 与父提交字节一致，未进入 delta）。

## 6. 门禁结果（最终树）

| 门 | 结果 |
|---|---|
| focused 自然序（3 文件） | 32/32 PASS |
| focused 反向序（3 文件） | 32/32 PASS |
| PW1-R2 auth interceptor/session 套件（Pw1R2AuthSessionClosure + InviteAuthoringClosure + Pw1R4B4RetailerPermissionContext） | 55/55 PASS |
| CredentialLifecyclePages + RetailerCredentialPages | 含于 focused 双序 PASS |
| 完整 `pnpm exec vitest run` | 27 文件 / 391/391 PASS |
| `pnpm build` | exit 0（首跑因测试文件 spy 类型 ELIFECYCLE 2 → 以工厂函数推导精确类型修复后 0） |
| `git diff --check` | clean |
| detect-secrets（4 个变更源文件） | 0 发现（3 处测试夹具假密串按仓库惯例 `// pragma: allowlist secret`） |
| UTF-8 / 无 BOM / 无 CR | 4 文件全过 |
| GitNexus detect_changes + re-analyze + status | 提交后执行（见下） |

## 7. 禁止项遵守

未启动产品运行时（无 backend/frontend/PG/Redis）；未运行 Playwright；
未修改冻结 Harness（j1h2b-forgot-reset/** 零改动）；未重跑 Lubuntu
权威旅程；未合并、未部署、未启动 H2-C。

## 8. 下一步

仅 Kilo H2-B-R3 源审；其后由 CTO 决定受控合并与（如授权）B1-R3
harness 的 V4 浏览器权威运行（V2/V3 证据链 + B1-R3 canonical 合同 +
本拦截器收口共同构成其前置）。
