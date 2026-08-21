# DC-12R1-MVP-L1-J1-H2-A — Retailer Invitation Authoring Closure

- 日期：2026-08-21（+08:00）
- 执行者：ZCode
- 任务：DC-12R1-MVP-L1-J1-H2-A（Retailer Invitation Authoring Closure）
- 产品基线（冻结）：`c5b66d26b83a0cc6170282de1e2fe281e448b2a8`（worktree 自该精确 SHA 创建）
- 证据引用：J1-H1-E1 @ `09b3f73e253f8ed384b4e0afd945b23ad9a4e2bd`
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-a-retailer-invitation-authoring-2026-08-21`
- 裁决目标：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_A_MERGE_REVIEW`

## 1. 根因与修复对象

F-13（用户症状）/ F-14（诊断证据）为同一根因：后端邀请 API 完整
（`backend/api/v1/invitations.py`：POST /invitations、POST /invitations/lookup、
revoke），但批发商侧"生产端"UI 整体缺失——前端零处调用 POST /invitations，
RetailerListPage 空态文案承诺 invitation link 却无任何 UI 能生成它。

本修复交付批发商侧邀请创建流程入口（Customers 流程内，不挂公共消费页到侧栏），
并交付规范化的公共消费端 `/invite`（fragment-only 凭据传递）。

## 2. Phase 1 — 证明与影响分析

1. `git fetch --all --prune`：完成（仅 reports 分支快进 328564e1→09b3f73e）。
2. 隔离 worktree 自精确 `c5b66d26` 创建：`_dc12r1_j1_h2a_invite_worktree`。
3. 漂移验证：`origin/product-dev-recovered` == `c5b66d26`（未漂移）。
4. GitNexus（index 15,248 nodes / 45,759 edges / 300 flows）upstream impact：
   - `RetailerListPage`：0 依赖方 → LOW
   - `AppRouter`：0 依赖方 → LOW
   - `InvitePage`：0 依赖方 → LOW
   - 邀请 API 层（`InvitationService`/repositories）：未被本任务修改
     （仅新增前端 adapter 与回归测试）。
   - 结论：无 HIGH/CRITICAL → 未触发 STOP_AND_REPORT_CTO。
5. 合同盘点（全部为既有合同，本任务零后端行为修改）：
   - `POST /invitations`：RBAC `invitations:create`；body =
     `InvitationCreateRequest`（snake_case，`retailer_phone?`/`expires_at?`）；
     201 → `DataResponse[InvitationData]`（snake_case 序列化）。
   - `POST /invitations/lookup`：公共；body `{code}`；lookup 数据含
     `usable/reason/status/wholesaler_id/wholesaler_name/expires_at`。
   - `POST /retailers/register`：公共；body
     `{invitation_code, phone, name?, email?, address?}`；原子接受
     （锁定→校验→零售商→绑定+租户用户+角色→setup token→SMTP→标记 used）。
   - `POST /retailers/setup-credential`、`/retail/login?w=<portal>`：既有页面。
   - `GET /invitations/{code}`：DEPRECATED（路径 token），仅旧消费端保留。
   - CamelModel 仅输入接受 camelCase、输出保持 snake_case（已按此对齐
     前端 payload/响应类型）。

## 3. 交付内容（精确文件清单）

新增：
- `frontend/src/pages/retailers/InviteCreatePage.tsx` — 批发商创建页
  （Customers 流程内，`/retailers/invite`）。
- `frontend/src/pages/invite/InvitationLandingPage.tsx` — 公共 `/invite`
  落地页（fragment 捕获→POST lookup→注册表单→生命周期指引）。
- `frontend/src/services/invitationService.ts` — 邀请 API adapter
  （仅包装 create/lookup；不包装 deprecated GET 路径 token 端点）。
- `frontend/src/utils/clipboard.ts` — 凭据安全剪贴板 helper（失败不外泄内容）。
- `frontend/src/tests/InviteAuthoringClosure.test.tsx` — T1–T9 前端证据测试
  （真实 AppRouter/守卫/页面/api adapter + 记录型 axios adapter）。
- `backend/tests/test_dc12r1_j1_h2a_cross_tenant_invitation_binding.py` —
  T10 跨租户后端回归锁（纯回归，无行为修改）。

修改：
- `frontend/src/pages/retailers/RetailerListPage.tsx` — "Invite a retailer"
  CTA（header + 空态），`can(user, 'invitations:create')` 门控。
- `frontend/src/router/AppRouter.tsx` — `/invite`（canonical）+
  `/retailers/invite`（WholesalerPermissionRoute 守卫）；`/invite/:code`
  标注 DEPRECATED 兼容入口。
- `frontend/src/router/guards.tsx` — 新增 `WholesalerPermissionRoute`
  （fail-closed 权限守卫，复用集中 `can()`）。
- `frontend/src/services/retailerService.ts` — `registerWithInvitation`
  （`invitation_code` 仅进 JSON body）。
- `frontend/src/utils/permissions.ts` — `INVITATION_PERMISSIONS`
  （与后端 RequirePermission 字节一致）。
- `frontend/src/utils/urlToken.ts` — fragment 参数支持 `code`；
  `code/invitation_code/invitationCode` 列入敏感 query 黑名单。

产品合同符合性：
- 表单字段严格复用 `InvitationCreateRequest`（仅两个可选字段，snake_case），
  无新增数据库字段、无 migration、无依赖/lockfile 变更。
- 无权限 fail closed（三层独立：路由守卫 → CTA 门控 → 后端
  RequirePermission），非仅按钮隐藏。
- 提交调用真实 `POST /invitations`；同步 in-flight 锁防双击重复；
  失败固定中性文案（不回显后端 message/request_id/响应体）。
- 成功面板显示状态/到期时间 + "Copy secure invite link" +
  "Copy invitation code"。

凭据安全合同：
- 新 UI 生成的链接唯一格式：`${origin}/invite#code=<opaque>`
  （绝不生成 `/invite/:code` 路径链接，绝无 query token）。
- 落地页启动即捕获 fragment 并 `replaceState` 清除地址栏；code 仅存
  短生命周期内存状态（不进 localStorage/sessionStorage）。
- 后续仅经 `POST /invitations/lookup` 与 `POST /retailers/register` 的
  JSON body 使用 code。
- 旧 `/invite/:code` 保留为明确 DEPRECATED 兼容入口（代码注释标注）。
- 二维码分享：因需新增前端依赖（现无 QR 库，lockfile 变更被任务禁止）
  → 按任务 3.9 记录为紧随其后的增强项，不阻塞本修复。

## 4. Phase 4 — 测试真实性

前端（真实 AppRouter + 真实守卫 + 真实 Customers/邀请页面 + 真实 api
adapter，HTTP 层为记录型 axios adapter，请求序/载荷/缺席断言均为证据级）：
- T1 有 `invitations:create` → CTA 可见可操作（`InviteAuthoringClosure`
  "T1: session with invitations:create…"）。
- T2 无权限 → CTA 隐藏 + `/retailers/invite` fail closed（页面不挂载、
  零 POST）。
- T3 精确一次 POST、payload 与后端合同逐字段一致（含空可选字段省略 T3b）。
- T4 双击（同 tick 两次 fireEvent.click）仅产生一次 POST。
- T5 失败固定中性文案（敌意 sentinel 后端体零回显）+ 重试成功。
- T6 fragment 捕获后立即清除（hash/search 归空）。
- T7 lookup 经 POST JSON body（body 精确 `{code}`；零路径 token GET）；
  T7b 注册 `invitation_code` 仅进 body、任何请求 URL 不含 code。
- T8 code 不入 storage/console/错误输出（console 五通道 spy + storage
  dump + DOM 断言）。
- T9 注册成功进入 register → setup-credential 指引 → `/retail/login`
  真实路由交接。
- 安全链接格式断言：`/invite#code=` 精确格式、非 `/invite/`、无 `?`。

后端（真实 PG16 + 真实 service/repository）：
- T10 邀请只能绑定到邀请方批发商 A（B 存在于同一注册表）；该零售商无
  任何其他 wholesaler 绑定行；邀请 terminal（used + used_retailer_id）。
- T10b used 后任何租户不可再消费（INVITATION_ALREADY_USED，无第二绑定）。
- T10c 公共 lookup 仅解析到邀请方 wholesaler（不可被引向其他租户身份）。

Mutation RED（每个突变临时施加→聚焦套件失败→还原；最终测试文件上复验
5/5 RED，还原后套件复绿）：
- M1 删除权限守卫（/retailers/invite 直接挂载）→ T2 RED。
- M2 恢复 path-token 链接（`/invite/${code}`）→ 安全链接格式测试 RED。
- M3 删除 URL 清除（fragment 保留）→ T6 RED。
- M4 删除 in-flight 锁 → T4 RED。
- M5 前端伪造成功（不调 POST /invitations）→ T3/T3b RED。

## 5. Phase 5 — 门禁结果

前端：
- 聚焦套件自然序：13/13。
- 聚焦套件反向序（逐条 last-to-first，退出码判定）：13/13。
- 聚焦套件 shuffle（`--sequence.shuffle --sequence.seed=20260821`）：13/13。
- 全量 vitest：25 files / 368 tests 全过（基线 355 + 本任务 13）。
- `pnpm build`（tsc + vite）：PASS。

后端（任务栈：h2a_pg16 PG16.14@15436 / h2a_redis7@6396，fresh
`test_h2a_a` 库 alembic 迁移至 head `037_payment_declarations_schema`，
worktree 自有 .venv 严格按 requirements.txt（bcrypt==4.0.1 pin）安装）：
- 聚焦回归自然序：6 文件 108/108
  （test_dc12r1_j1_h2a_cross_tenant_invitation_binding /
  test_dc1g_retailer_registration_binding_balance /
  test_dc12r1_s1_retailer_identity /
  test_route_authorization_policy（RBAC）/
  test_dc12r1_s1_r5a_permission_registry_parity /
  test_dc12r1_s2_supplier_scoped_retailer_login）。
- 聚焦回归文件倒序：108/108。
- 两套完整后端套件：未执行——本任务未修改任何后端行为代码
  （仅新增回归测试文件），按任务 Phase 5.5 条款豁免。

卫生门禁：
- `py_compile`（新增后端测试文件）：OK。
- `git diff --check`：无空白错误。
- pre-commit（trailing-whitespace / end-of-file-fixer / check-yaml /
  large-files / detect-secrets baseline）：全过。
- detect-secrets：Passed（含 baseline）。
- UTF-8/mojibake：12 个变更文件严格 UTF-8、无 BOM、无替换符/双重编码
  痕迹。

GitNexus：
- 提交前 `gitnexus detect_changes`：CLI 无该子命令（仅 MCP 提供）——
  如实披露；以精确 `git diff --cached`（--stat 全清单见上）替代。
- 提交后 `gitnexus analyze` + `status`：重新索引完成（见第 7 节）。

## 6. 环境与范围披露

- 环境为本任务专属 Docker 栈（PG16.14-alpine @127.0.0.1:15436、
  redis:7-alpine @127.0.0.1:6396），非共享既有栈；测试库为一次性
  `test_h2a_a`（tester 超级用户属主，任务后可随栈销毁）。
- 主仓既有 .venv 的 bcrypt 版本与冻结产品不兼容（passlib 72 字节强制），
  故为 worktree 建立独立 .venv 并按冻结 requirements.txt 安装——该目录
  被忽略，不入提交。
- 全局 axios 拦截器对 5xx 显示瞬态 toast（既有全局基建，auto-dismiss，
  全站共享）——非本任务产物，未修改；本任务页面自身失败面已证明零
  敌意载荷回显（测试中以清空 toast store 后的全 DOM 断言证明）。
- 范围禁令遵守：未触碰 pricing/SKU/barcode/custom fields/password reset
  (F-05)/platform-admin/migration-model-schema/dependency-lockfile/部署/
  162-node 矩阵；未将公共消费页挂到批发商侧栏。

## 7. 交付证明

- 文件清单与 SHA-256：见 `manifest_sha256.txt` 同批附件（本 ledger 同
  commit）。
- local == remote：commit 后 `git rev-parse HEAD` ==
  `git rev-parse origin/<branch>` 证明（见 commit 后置记录）。
- protected refs 未变：`origin/product-dev-recovered` 仍 == `c5b66d26`。

## 8. 后续顺序

H2-A（本任务）→ Kilo 有界源码审查 → OpenCode focused browser lifecycle →
J1-H2-B password-reset causal closure → 恢复人工旅程 Step 5–12。

增强项记录（不阻塞）：邀请二维码分享（需新增依赖 + 单独定义 token
生命周期/防重放/泄漏合同，CTO 另批）。
