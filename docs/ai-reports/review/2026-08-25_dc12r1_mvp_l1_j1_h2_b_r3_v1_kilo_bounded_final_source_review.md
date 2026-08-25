# DC-12R1-MVP-L1-J1-H2-B-R3-V1 — Kilo Bounded Final Source Review

- 日期：2026-08-25（+08:00）；审查者：Kilo
- 模式：源码真实性审查（冻结状态，只读审查，不运行测试、不合并、不部署）
- 审查对象：`0267ea73b77c1246232124278892de11739f408e`
- 父提交：`8c7e84779cc1810baab32859d3dc353e1028384a`（B1-R3 冻结点）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r3-public-password-recovery-interceptor-closure-2026-08-25`

## 执行边界声明

- **未运行 Playwright**（无 `npx playwright test`、无浏览器旅程、无运行时 JSON/JUnit）
- **未启动产品运行时**（无 backend、无前端 dev server、无 PG/Redis、无邮件 sink）
- **未合并、未部署、未启动 H2-C**
- 仅完成源码级真实性审查

## 冻结输入

| 项目 | 值 |
|------|-----|
| 候选 | `0267ea73b77c1246232124278892de11739f408e` |
| 父提交 | `8c7e84779cc1810baab32859d3dc353e1028384a` |
| 分支 | `zcode/dc12r1-mvp-l1-j1-h2-b-r3-public-password-recovery-interceptor-closure-2026-08-25` |
| B1-R3 候选 | `8c7e84779cc1810baab32859d3dc353e1028384a` |
| V2 STOP | `3fb185be25b51ae4554c58e8c06c795673c058dd` |
| V3 STOP | `888fd2072afd77d54881e834c592a4b0f587b271` |
| Lubuntu STOP | `f7dd9aa3331217af2f5cab68dad7aa533093401f`（按台账引用） |

## Phase 1 — Proof And Scope

| 步骤 | 结果 | 证据 |
|------|------|------|
| `git fetch --all --prune` | 通过 | 远程分支存在且候选等于 branch tip |
| 候选 == remote branch tip | 通过 | `0267ea73` == `origin/zcode/...` |
| `candidate^` == `8c7e847` | 通过 | `git rev-parse HEAD~1` = `8c7e847` |
| delta 恰好 5 个文件 | 通过 | `git diff --name-status 8c7e847..0267ea7` = 5 文件 |
| 产品文件仅 `frontend/src/services/authService.ts` | 通过 | 其余 4 文件为测试/台账 |
| api.ts / backend / harness / 依赖 / lockfile 零改动 | 通过 | `git diff --name-only` 确认无此类路径 |
| 候选 SHA 未修改 | 通过 | 只读审查，未修改工作树 |

### Delta 文件清单（5 文件）

1. `ai-ledger/product-ai/2026-08-25_dc12r1_mvp_l1_j1_h2_b_r3_public_password_recovery_interceptor.md` — 新增台账
2. `frontend/src/services/authService.ts` — **产品修复**：四个公共恢复调用加 `{ headers: { Authorization: '' }, skipAuthInterceptors: true }`
3. `frontend/src/tests/CredentialLifecyclePages.test.tsx` — 最小更新：forgot/reset 断言补第三参
4. `frontend/src/tests/PublicPasswordRecoveryInterceptor.test.tsx` — **新增**：T1-T6 真实拦截器测试
5. `frontend/src/tests/RetailerCredentialPages.test.tsx` — 最小更新：retailer reset 断言补第三参

## Phase 2 — Four Public Recovery Calls Explicit Empty Authorization + skipAuthInterceptors

| 调用 | 端点 | Authorization | skipAuthInterceptors | 证据 |
|------|------|---------------|---------------------|------|
| `forgotPassword` | `/auth/forgot-password` | `''` (explicit empty) | `true` | `authService.ts:54-58` |
| `resetPassword` | `/auth/reset-password` | `''` (explicit empty) | `true` | `authService.ts:60-64` |
| `retailerForgotPassword` | `/client/auth/forgot-password` | `''` (explicit empty) | `true` | `authService.ts:77-84` |
| `retailerResetPassword` | `/client/auth/reset-password` | `''` (explicit empty) | `true` | `authService.ts:86-93` |

**关键证据：**
- `authService.ts` diff 显示四个调用统一添加 `{ headers: { Authorization: '' }, skipAuthInterceptors: true }`
- 注释明确：`// DC-12R1-MVP-L1-J1-H2-B-R3: public password-recovery calls are anonymous by contract.`
- `api.ts` request interceptor (line 56): `if (config.headers && !config.headers.has('Authorization'))` — explicit empty string causes `has('Authorization')` to return `true`,所以 stale store token 不注入（PW1-R2-R2 大小写不敏感优先级）
- `api.ts` response interceptor (line 119): `if (originalRequest?.skipAuthInterceptors) { return Promise.reject(error); }` — 401 原样 reject，不触 toast/refresh/queue/logout

## Phase 3 — Anonymous 401 Does Not Trigger Side Effects

| 副作用 | 预期 | 证据 |
|--------|------|------|
| refresh | 不发生 | `api.ts:119` skip 请求直接 reject，不进入 line 152+ 的 refresh 路径 |
| queue | 不发生 | 同上，不进入 line 164+ 的 failedQueue 路径 |
| logout | 不发生 | 同上，不进入 line 177+ 的 logout 路径 |
| toast | 不发生 | 同上，不进入 line 126+ 的 toast echo 路径 |
| navigation | 不发生 | 同上，不进入 line 184/187/221/223 的 `window.location.href` 路径 |

**测试证据：**
- T1 (line 176-201): 断言 `POST /auth/refresh` 零调用、`POST /auth/logout` 零调用、`useToastStore.getState().toasts` 空、`snapshotSession()` 与 before 相等、navigation attempts 零
- T3 (line 227-252): 零售商侧同理，断言 `POST /auth/refresh`/`POST /auth/logout` 零调用、toasts 空、session 不变、navigation 零

## Phase 4 — Normal Protected Interface 401 Refresh/Retry Contract No Regression

| 合同 | 状态 | 证据 |
|------|------|------|
| 401 触发 refresh |  intact | `api.ts:152-228` 未修改；refresh 逻辑完整 |
| refresh 成功后重试原请求 | intact | `api.ts:212-213` `originalRequest.headers.set('Authorization', 'Bearer ${newAccessToken}'); return api(originalRequest);` |
| refresh 失败则 logout + 导航 | intact | `api.ts:214-228` 保持原逻辑 |
| 请求队列 | intact | `api.ts:88-102` `failedQueue` + `processQueue` 未修改 |
| 非 401 错误 toast | intact | `api.ts:126-150` toast echo 未修改 |

**测试证据：**
- T5 (line 302-334):  seeding stale session, GET `/dashboards/summary` 返回 401, 断言 `POST /api/v1/auth/refresh` 恰好 1 次, GET 恰好 2 次（首次 401 + retry 200）, retry 请求携带 `Bearer fresh-access-token`, store 更新为新 token

## Phase 5 — No Out-of-Bounds Changes

| 路径类别 | 变更 | 证据 |
|----------|------|------|
| api.ts | 零改动 | `git diff --name-only` 确认 |
| backend | 零改动 | `git diff --name-only` 确认 |
| 冻结 harness (`j1h2b-forgot-reset/**`) | 零改动 | `git diff --name-only` 确认 |
| 依赖 (`package.json`, `pnpm-lock.yaml`) | 零改动 | `git diff --name-only` 确认 |
| 其他产品路径 | 零改动 | delta 仅 5 文件，且仅 1 个产品文件 |

**关键发现：** 修复位于调用方配置（caller-side fix），未引入任何 URL 白名单，未修改 `api.ts`，未修改后端。

## Phase 6 — 6 New Tests Use Real Interceptors and Real Pages

| 测试 | 真实性证据 |
|------|-----------|
| T1 | 真实 `ResetPasswordPage` 渲染 + 真实 `api` 实例 + recording adapter；`authService` 不 mock |
| T2 | 同上 |
| T3 | 真实 `RetailerResetPasswordPage` 渲染 + 真实 `api` 实例 + recording adapter |
| T4 | 直接调用 `authService.forgotPassword/resetPassword/retailerForgotPassword/retailerResetPassword`（不 mock） |
| T5 | 直接调用 `api.get`（真实实例）+ recording adapter 模拟 401 然后 200 |
| T6 | 真实 `ResetPasswordPage` 渲染 + 真实 `authService.resetPassword` 调用 |

**关键证据：**
- 文件头注释（line 1-28）：`Runs against the REAL api.ts interceptors... and the REAL rendered pages. authService is NOT mocked.`
- `installAdapter` (line 74-93): 在真实 `api.defaults.adapter` 和 `axios.defaults.adapter` 上安装 recording adapter
- T4 (line 258-296): 直接循环调用 `authService` 四个方法，不 mock
- T5 (line 302-334): 直接调用 `api.get('/dashboards/summary')`，验证 refresh 路径
- 无 `vi.mock('@/services/api')` 或 `vi.mock('@/services/authService')`

## Phase 7 — M1-M5 Mutation Gates Hit Fix Points and Restore Byte-Consistent

| 门 | 变异目标 | 修复点 | RED 证据 | 恢复证据 |
|----|----------|--------|----------|----------|
| M1 | `resetPassword` 删 `skipAuthInterceptors` | `api.ts:119` skip 检查 | T1/T4 失败（2 failed） | 6/6 GREEN |
| M2 | 四调用删显式空 `Authorization` | `api.ts:56` request interceptor 注入 | T4 失败（1 failed，stale 边界） | 6/6 GREEN |
| M3 | `retailerResetPassword` 删 `skip` | `api.ts:119` skip 检查 | T3/T4 失败（2 failed） | 6/6 GREEN |
| M4 | `api.ts` 删 skip 旁路 | `api.ts:119-121` 直接 return | 3 failed | 6/6 GREEN |
| M5 | `ResetPasswordPage` 弱化中性文案 + 强制导航 | `ResetPasswordPage.tsx:64,72` 固定文案 | T1/T3 失败（2 failed） | 6/6 GREEN |

**关键证据：**
- 台账 (line 70-78): 明确记录每个变异的目标文件和 RED->GREEN 结果
- 恢复后字节一致性 (line 80-81): `mutation-snapshots.txt` 记录；`api.ts`/`ResetPasswordPage.tsx` 与父提交字节一致，未进入 delta
- 从源码验证修复点可达性：
  - M1/M3/M4: 移除 `skipAuthInterceptors` 或删除 api.ts line 119-121 会使请求进入 line 152+ 的 401 处理路径，触发 refresh/toast/logout/navigation，T1/T3/T4 断言失败
  - M2: 移除空 Authorization 会使 api.ts request interceptor line 56-61 注入 stale store token，T4 断言 `authorization` 为空失败
  - M5: 弱化 ResetPasswordPage.tsx line 64/72 的中性文案会使 T1/T3 的 `screen.findByText(NEUTRAL_ERROR)` 失败

## Phase 8 — Historical Rulings

| 历史裁决 | 当前状态 |
|----------|----------|
| Kilo B1-R3 PASS (`8c7e847`) | 父提交，未修改 |
| V2 STOP (`3fb185be`) | 保留，未修改 |
| V3 STOP (`888fd207`) | 保留，未修改 |
| Lubuntu STOP (`f7dd9aa3`) | 保留，未修改 |

## 裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R3_V1_KILO_BOUNDED_FINAL_SOURCE_REVIEW
```

- 候选 `0267ea73` 通过全部 Phase 1-7 源码真实性审查。
- 四个公共恢复调用均显式携带空 Authorization + `skipAuthInterceptors: true`。
- 匿名 401 通过 `api.ts` 双重旁路（request interceptor 不注入 token + response interceptor 直接 reject）确保不触发 refresh/queue/logout/toast/navigation。
- 普通受保护接口 401 refresh/retry 合同未修改，T5 验证 intact。
- 仅 5 文件 delta，api.ts/backend/harness/依赖/lockfile 零改动，caller-side fix，无 URL 白名单。
- 6 个新测试（T1-T6）使用真实 api.ts 拦截器 + recording adapter + 真实页面渲染，authService 不 mock，非 mock-only 假绿。
- M1-M5 突变门禁从源码分析确认命中修复点，台账记录 RED->GREEN，恢复后字节一致。
- 未运行 Playwright、未启动产品运行时、未合并、未部署。
