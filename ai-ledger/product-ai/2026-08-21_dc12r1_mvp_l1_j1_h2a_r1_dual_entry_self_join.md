# DC-12R1-MVP-L1-J1-H2-A-R1 — Dual-Entry Retailer Self-Join and Invitation Closure

- 日期：2026-08-21（+08:00）
- 执行者：ZCode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-a-r1-dual-entry-self-join-2026-08-21`
  （自 checkpoint `d58fd71a` 创建；累计审查基线 `c5b66d26..HEAD`）

## 谱系裁决（按新合同明确措辞）

- `c27224c3`（原 H2-A）：**SUPERSEDED / NO_PASS** — 不得作为合并候选消费。
- `d58fd71a`（precontract checkpoint）：**STOP_CHECKPOINT_ONLY / NO_PASS** —
  仅为工作保存点，不构成任何裁决。
- 本任务完成前，本分支亦为 NO_PASS；最终裁决以本台账门禁记录为准。

## Phase 0 — 合同证明门（编码前完成，全部证明，未触发 STOP）

**P0-1 pending/active 生命周期，无迁移：可行。**
`wholesaler_retailer_bindings.status`（VARCHAR(32)，现默认 'active'）已存在；
租户用户在 setup-credential 消费前 `is_active=false`（DC-12R1-S1 既有模式，
`test_pending_user_cannot_authenticated` 锁定"验证前无业务会话"）。加入
生命周期 = binding 'active' + pending user → setup 邮件 → 激活；事后停用 =
binding.status → 'inactive'（UPDATE，无 DDL）。

**P0-2 wholesaler code 安全预览合同：可行。**
`public.wholesalers` 已有 code/name/address/contact 列。新公共端点仅返回
{name, region(=address 摘要), contact_masked(脱敏)} + join_intent + 过期时间；
未知 code 返回同形中性 `{found:false}`（无身份披露、无 reason 回显）；限流
为防批量枚举主控制。

**P0-3 短期签名 join_intent：可行。**
无状态 HMAC：payload `{v, wholesaler_id, code, exp, jti}` base64url +
HMAC-SHA256（密钥自 `settings.SECRET_KEY` 派生，域分隔前缀
`join_intent:v1`，与 JWT 用途分离）；TTL 15 分钟；验证 = 常数时间签名比对 +
exp 校验 + 服务端解析 wholesaler_id。篡改/过期 → 中性拒绝。无新表。

**P0-4 二选一 + 拒绝前端 wholesaler_id：可行。**
注册请求 schema 不含 wholesaler_id 字段（pydantic 忽略未知字段且永不读取）；
服务端显式校验 invitation_code 与 join_intent 恰好其一（both → 422，
neither → 422）；绑定 wholesaler 只能来自服务端验证的邀请或 join_intent。

**P0-5 唯一性/幂等/限流/事后停用：可行。**
- 唯一性：DB 约束 `uq_wholesaler_retailer`（竞态安全兜底）。
- 幂等：注册对已存在绑定返回既有关系（成功语义）；前端内存幂等键 +
  in-flight 锁防双击（双 POST 不产生第二关系）。
- 限流：全局 RateLimitingMiddleware 之外，为 lookup-code 与 register 增加
  独立 Redis 固定窗口桶（端点独立 key 命名空间）实现"分别限流"。
- 事后停用：新端点 gated by 新权限码 `retailers:deactivate`（加入主
  ADMIN_PERMISSIONS 元组；u1 合同满足——端点消费该码，非 extra）；
  bootstrap 脚本按 S2B-I1 先例幂等授予既有租户 admin（脚本修改非迁移）；
  未重跑 bootstrap 的租户 403 fail-closed（安全默认）。

**P0-6 无迁移整体可行性：可行。**
上述全部为代码级变更（schema 响应字段、新公共端点、HMAC helper、注册
合同收紧、bootstrap 授权块）。加入来源（invite/code）展示由
`invitations.used_retailer_id` 关联推导（JOIN 查询，无新列）。
禁止项遵守：无 migration/model/schema/lockfile 变更。

**Phase 0 结论：六项全部证明 → 进入实现。**

## 实现（c5b66d26..HEAD 累计 + 本 delta）

后端（行为变更，完整双栈门禁已执行）：
- `core/join_intent.py`（新）：无状态 HMAC join_intent（域分隔密钥、15 分钟
  TTL、常数时间比对、中性失败）。
- `api/v1/public_join.py`（新）：公共 `POST /wholesalers/lookup-code` ——
  安全预览（名称/地区摘要/脱敏联系）+ 签名 intent；未知 code 同形中性；
  端点级限流（10/min/IP，独立 Redis 桶）。该端点置于独立路由文件：u6h2
  治理合同禁止修改 `api/v1/wholesalers.py`（首次全量跑发现，已整改——
  wholesalers.py 还原为基线原样）。
- `core/rate_limiter.py`：增量 `check_endpoint_rate_limit`（端点独立桶）。
- `schemas/retailer.py`：注册合同——email 必填（EmailStr）、
  invitation_code/join_intent 严格二选一（model_validator）、无
  wholesaler_id 字段、响应含服务端 wholesaler_code；列表项含 join_source。
- `api/v1/retailers.py`：双入口注册分发（intent 验证失败中性 400；
  EMAIL_REQUIRED 422）；`POST /retailers/{id}/deactivate`（租户隔离
  中性 404、幂等）；列表 join_source 推导（used-invitation 关联，无新列）。
- `services/retailer_provisioning_service.py`（CRITICAL 影响符号——仅增量
  方法 `register_with_join_intent` + email 必填守卫 + ProvisioningResult
  扩展字段；既有路径语义未变）；`services/retailer_service.py` 包装器。
- `core/permission_registry.py`：主 ADMIN_PERMISSIONS 增
  `retailers:deactivate`（r5a parity 钉死的仅 MANAGEMENT 子集，未触碰）；
  `scripts/bootstrap_tenant_schema.py` 按 S2B-I1 先例幂等授予既有租户
  admin（脚本非迁移；未重跑 bootstrap 的租户 403 fail-closed）。
- 测试库存更新：route-authorization-policy 与 u6f 的公共路径清单增列
  lookup-code（新合同 CTO 已批准）。

前端：
- `pages/retailer/RetailerJoinPage.tsx`（新，公共 `/retail/join`）：双入口
  （邀请链接/码粘贴 → POST /invitations/lookup；供应商码 → 预览 + 显式
  确认 → join_intent 注册）；email 必填；in-flight 锁；空 Authorization +
  skipAuthInterceptors；注册后 `?w=<响应验证 code>` 门户交接。
- `pages/retailers/InviteCreatePage.tsx`：Web Share API 分享（移动端可选
  WhatsApp 等；失败回退复制；无 wa.me query / 无 WhatsApp Business API）。
- `pages/retailers/RetailerListPage.tsx`：Joined via（Invite link /
  Supplier code）列 + 权限门控停用按钮（中性失败文案）。
- `services/selfJoinService.ts`（新）/ `retailerService.ts` / `api.ts`
  （skipAuthInterceptors 通道，自 checkpoint 继承并保留）。
- 原 H2-A 缺陷 1–7 全部关闭（email 必填前后端 RED、内存 code 重试、空
  Authorization、toast 中立化、T8 无清空断言、服务端验证 portal w、
  manifest/HEAD/GitNexus 一致性——见交付证明）。

## 强制测试与 mutation

- 前端证据套件：InviteAuthoringClosure（18）+ DualEntrySelfJoin（11）=
  29 项，真实 AppRouter/守卫/页面/api adapter；T1–T14 全映射（T13 跨租户
  由后端真实 PG 测试承载 + 前端 payload 无 wholesaler_id 断言）。
- 后端证据：`test_dc12r1_j1_h2a_r1_dual_entry_self_join.py`（15）——
  intent 原语（往返/篡改签名/篡改 payload/过期/畸形）、安全预览与中性
  miss、二选一与 ghost-wholesaler_id 免疫、email 必填 RED、篡改不绑定、
  幂等（同一 binding id）、租户隔离停用、join_source 推导、限流接线。
- Mutation RED 9/9：权限门控（deactivate 无权限渲染）、email required
  （landing+join 两页）、portal w、toast 中立化、Authorization 隔离、
  幂等锁（同步双 form.submit 绕过 disabled）、URL scrub、
  join_intent 签名验证（后端，篡改测试转绿为 BAD 后确认 RED）。

## 门禁结果（权威）

- 前端聚焦：自然 29/29；shuffle(seed 20260821) 29/29；逐条反向 29/29。
- 后端聚焦（9 文件 150 项）：自然 150/150；文件倒序 150/150。
- 完整前端 vitest：26 files / **384/384**；`pnpm build` PASS。
- 完整后端 · 栈 A（PG16.14@15436 + redis7@6396，fresh `test_h2a_r1`，
  alembic 037 head，完整 env 配方含 TEST_DATABASE_URL /
  MPANGO_ALLOW_TEMP_DB_CREATE / PW1R3_TEST_REDIS_URL）：
  **3669 passed / 1 failed / 48 skipped / 15 xfailed / 0 errors**——唯一
  失败为 `test_dc12r1_contract_d_statement_print.py` 的既有可能性断言
  （响应中随机 UUID 恰含子串 "1000"，与本 delta 无关；单独重跑 3/3 通过；
  记录为 pre-existing flake，不在本任务范围修改）。
- 完整后端 · 栈 B（PG16.14@15437 + redis7@6397，fresh `test_h2a_r1_b`，
  同一生命周期）：**3670 passed / 0 failed / 48 skipped / 15 xfailed**。
- 两栈 skip 集一致（48=48）。
- py_compile（全部变更 py）；git diff --check 干净；pre-commit 全过
  （trailing-whitespace 自动修正 rate_limiter.py 后复验编译 OK）；
  detect-secrets（baseline）通过；23 变更文件严格 UTF-8、无 BOM、无
  mojibake。

## 环境披露

- 任务栈（两套，均为任务专属一次性容器）：h2a_pg16@15436/h2a_redis7@6396、
  h2a_r1_pg16_b@15437/h2a_r1_redis7_b@6397；库 test_h2a_r1/_b（属主
  tester，临时口令 testerpw 随容器销毁）。
- worktree venv 按 freezing requirements.txt 安装；另装测试依赖
  `hypothesis`（仅测试环境，venv gitignored，无 lockfile 变更）。
- 首次全量跑暴露两类环境缺口（TEST_DATABASE_URL / temp-db 开关）与两处
  真实治理冲突（u6f 第二份公共清单、u6h2 禁改 wholesalers.py）——均已按
  合同整改并在两套全量门禁中验证。
- GitNexus impact：RetailerRegisterRequest LOW、register_with_invitation
  LOW、RetailerService HIGH、RetailerProvisioningService CRITICAL——
  后者采用"仅增量方法"策略缓解并在双栈全量门禁中验证零回归。

## 交付证明

- committed-blob manifest：`manifest_sha256_h2a_r1.txt`（git cat-file blob
  SHA-256，missing=0 / mismatch=0 验证记录见下）。
- GitNexus analyze/status：indexed commit == 最终 HEAD（钉住证明见下）。
- local == remote 与 protected refs 未变证明见下（push 后记录）。
- 裁决目标：PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2A_R1_DUAL_ENTRY_MERGE_REVIEW
  （Kilo 有界累计源码审查基线：c5b66d26..HEAD）。
