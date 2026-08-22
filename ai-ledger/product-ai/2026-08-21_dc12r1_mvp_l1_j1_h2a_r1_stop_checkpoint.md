# DC-12R1-MVP-L1-J1-H2-A-R1 — STOP CHECKPOINT（合同重对齐前冻结）

- 日期：2026-08-21（+08:00）
- 执行者：ZCode
- 指令：STOP DIRECTIVE — DC-12R1-MVP-L1-J1-H2-A-R1 CONTRACT REALIGNMENT
- 分支（checkpoint）：`zcode/dc12r1-mvp-l1-j1-h2-a-r1-precontract-stop-2026-08-21`
  （自 `c27224c3` 创建，携带未提交 R1 工作）
- 原工作分支：`zcode/dc12r1-mvp-l1-j1-h2-a-retailer-invitation-authoring-2026-08-21`
  （HEAD = `c27224c3`，未移动，远程在位）

## 裁决标记

**NO_PASS / SUPERSEDED_PENDING_NEW_CONTRACT**

- 本 checkpoint 不构成任何合并裁决：`c27224c3` 与本 checkpoint 分支均
  **不是 merge-ready**，不得据此进入 Kilo merge review。
- 原 H2-A 的 `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_A_MERGE_REVIEW` 裁决状态
  冻结待定（pending）：CTO 指令"合同重对齐"意味着 R1 所依据的入口合同
  将被新合同取代；在新合同落地前，原 PASS 不应被消费。
- 下一步必须等待新合同任务书；不得开始 OpenCode browser lifecycle 或
  J1-H2-B。

## STOP 时点的工作状态（相对 c27224c3 的未提交修改，11 文件，+546/-98）

后端（行为变更，未过完整门禁）：
- `backend/schemas/invitation.py`：`InvitationLookupData` 新增可选
  `wholesaler_code`。
- `backend/api/v1/invitations.py`：两个 lookup 端点填充
  `wholesaler_code`。
- `backend/services/onboarding_service.py`：`build_retailer_setup_link`
  支持在 fragment 追加 `w=<code>`。
- `backend/services/retailer_provisioning_service.py`：注册与 reissue
  两条邮件链传递邀请方 portal code。
- `backend/tests/test_dc12r1_j1_h2a_cross_tenant_invitation_binding.py`：
  扩展（setup 邮件链接 w= 断言 + HTTP 层 lookup wholesaler_code 测试）。

前端（未过完整门禁）：
- `InvitationLandingPage.tsx`：email 必填、wholesaler_code 验证
  （^[A-Z0-9]+$，fail closed）、lookup 重试复用内存 code（不 reload）、
  注册完成跳 `/retail/login?w=<verified-code>`。
- `RetailerSetupCredentialPage.tsx`：fragment 捕获 `w`，设置密码完成后
  门户跳转（无 w 的旧链接保持原行为）。
- `services/api.ts`：新增 `skipAuthInterceptors` 选择退出通道（无 toast
  回显、无 401 refresh 劫持）。
- `services/invitationService.ts` / `services/retailerService.ts`：公共
  调用显式空 Authorization + 全拦截器退出。
- `src/tests/InviteAuthoringClosure.test.tsx`：R1 测试族。

## STOP 前已执行的测试（结果如实）

- 后端聚焦（本文件，任务栈 fresh DB）：4/4 通过。
- 前端聚焦自然序：18/18。
- 前端聚焦 shuffle（seed 20260821）：18/18。
- 全量前端 vitest：25 files / 373/373。
- `pnpm build`：PASS。
- 前端反向序：**中途被 STOP 取消**（取消前无失败记录，未完成）。
- 后端聚焦双序、两套完整后端门禁、R1 突变 RED 复验：**未执行**（STOP）。
- GitNexus impact（R1 后端符号）：已执行（build_retailer_setup_link
  LOW；InvitationLookupData MEDIUM；端点 LOW）。

## 任务自有运行时资源（STOP 时处置）

- Docker：`h2a_pg16`（postgres:16-alpine，127.0.0.1:15436）、
  `h2a_redis7`（redis:7-alpine，127.0.0.1:6396）——任务专属一次性栈，
  已随本 checkpoint 销毁（docker rm -f）。
- 一次性测试库：`test_h2a_a`（属主 tester；临时口令 testerpw 仅用于该
  一次性容器，随容器销毁失效；未写入任何提交文件）。
- worktree venv：`backend/.venv`（gitignored，按冻结 requirements.txt
  安装；保留在 worktree，不入库）。
- 未提交任何 .env / token / 身份文件 / 邮件 / 运行时日志。

## 后续

等待 CTO 新合同任务书（dual-entry contract 重对齐）；新任务基于本
checkpoint 或 `c27224c3` 起算，由新任务书指定。
