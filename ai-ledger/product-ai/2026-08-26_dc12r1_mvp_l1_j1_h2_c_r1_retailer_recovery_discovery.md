# DC-12R1-MVP-L1-J1-H2-C-R1 — 零售商恢复发现实现（候选）

- 日期：2026-08-26（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1（Retailer Password-Recovery Discovery
  Implementation）；风险等级 P1 AUTH / PUBLIC RECOVERY
- 验证层级：V3_MERGE_CRITICAL；CLAIM_CEILING：
  `CANDIDATE_READY_FOR_KILO_SOURCE_REVIEW`
- PARENT：`b2d28f320c7428e7e81f7cb2033c99b1aa4471dd`（本地 == 远端复核）
- 受保护基线：`origin/product-dev-recovered@2c20d58c…`（为 PARENT 祖先；
  全程未变）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-retailer-recovery-discovery-2026-08-26`

## 1. 变更范围（恰 12 个授权文件）

产品（6）：
1. `frontend/src/router/AppRouter.tsx` — 新公共路由
   `/retailer/forgot-password`。
2. `frontend/src/pages/client/ClientLoginPage.tsx` — 仅有效 portalCode 下
   渲染 Forgot password 入口（`/retailer/forgot-password?w=<NORMALIZED>`）。
3. `frontend/src/pages/retailer/RetailerForgotPasswordPage.tsx`（新增）—
   复用 trim→UPERCASE→`^[A-Z0-9]+$` 语义；无效/缺失/畸形 `w`（含
   `w=BAD%21`）中性无效门户状态、零 recovery POST；仅调用既有
   `authService.retailerForgotPassword`；固定中性文案；ref 同步防重
   （双击单 POST）。
4. `frontend/src/pages/retailer/RetailerResetPasswordPage.tsx` — scrub 前
   从 fragment 读 w（内存保存）；成功 CTA `/retail/login?w=<CODE>`；
   legacy（无/畸形 w）有效 token 仍可重置，成功后仅中性指引、无
   `/login` CTA、不猜门户；resetToken 不入 query/storage/log/console/
   network metadata，w 不入 POST body/storage/log。
5. `backend/services/onboarding_service.py` —
   `build_retailer_reset_link(token, settings=None, wholesaler_code=None)`
   向后兼容；提供 canonical code 时生成
   `/retailer/reset-password#resetToken=<SECRET>&w=<CODE>`（沿
   setup-link 的 `quote(code, safe='')` 先例）。
6. `backend/services/retailer_provisioning_service.py` —
   `_find_verified_retailer_for_wholesaler` 同时返回匹配行的 canonical
   `w.code`；邮件链接使用 DB canonical 代码（小写调用输入 → DB 大写
   canonical），绝不回显调用方原始大小写。

测试（5）：新增 `RetailerPasswordRecoveryDiscovery.test.tsx`（20 节点，
HC01-HC16 前端覆盖 + M3/M9 锚点）与
`test_dc12r1_j1_h2c_retailer_recovery_discovery.py`（HC11/HC17 + M4/M5
锚点 + legacy 形状）；更新 `RetailerCredentialPages`、
`PublicPasswordRecoveryInterceptor`（新增 T3.5 零售商成功回门户）、
`Dc12r1S2RetailerPortal`（入口可见性）。
台账（1）：本文件。`authService.ts`、j1h2b-forgot-reset harness、
migration/model/schema/dependency/lockfile 均零改动（diff 复核）。

## 2. Phase 1 证明

- PARENT/受保护基线远端复核一致；基线为 PARENT 祖先。
- 脱敏 `preflight.json`：仅记录变量存在性（DATABASE_URL/REDIS_URL/
  PUBLIC_FRONTEND_URL/SMTP_HOST/PW1R3_TEST_REDIS_URL/TEST_DATABASE_URL
  全部未设置于宿主环境）。
- GitNexus @ PARENT 重建（28,900 nodes / 60,266 edges）；五符号 upstream
  impact：全部调用者闭合于 allowlist（AppRouter 由 App.tsx 挂载不变；
  P25 清单只钉平台路由，公共路由不受影响）。无 HIGH/CRITICAL、无
  allowlist 外直接调用者，未触发 STOP。

## 3. 真实测试与变异门（Phase 3）

- 无 skip/xfail/conditional pass。
- 变异门 M1-M9 全部 RED 后按冻结 blob 快照逐字节恢复：

| 变异 | 内容 | RED | 恢复 |
|---|---|---|---|
| M1 | 删除有效门户忘记密码入口 | 3 failed | byte-identical |
| M2 | 无效门户仍显示入口 | 2 failed | byte-identical |
| M3 | 忘记页泄露 raw error | 1 failed | byte-identical |
| M4 | reset 邮件删除 w | 3 failed | byte-identical |
| M5 | 邮件回显调用方小写代码 | 2 failed | byte-identical |
| M6 | scrub 后读 w（live window.location） | 1 failed | byte-identical |
| M7 | 成功 CTA 恢复 /login | 3 failed | byte-identical |
| M8 | legacy 判无效 | 2 failed | byte-identical |
| M9 | 删除单次提交保护 | 1 failed | byte-identical |

注：M6 首次以 location 属性快照重排未触发 RED（prop 为不可变快照，
重排无语义差）；以真实缺陷形态（scrub 后读 live `window.location.hash`）
重验为 RED。HC06 双击以单 act 批内两次 click 触发，使 M9 确定可检。

## 4. 候选门（Phase 4）

- 前端 focused：自然序 4 文件/59 测试 + 明确反向序 4 文件/59 测试 全绿。
- 全量 frontend vitest：28 文件 / 416 测试全绿；`pnpm build` 成功。
- 任务自有 fresh 栈：PG16（127.0.0.1:15455）+ Redis7（127.0.0.1:16405）；
  Alembic 唯一 head `037_payment_declarations_schema`。
- 任务自有 venv（Python 3.12.10 + 锁定 requirements，bcrypt 4.0.1 —
  共享宿主 venv 的 bcrypt 5.0.0/passlib 1.7.4 组合无法运行既有套件，
  属 H7 已记录的清单漂移，不在本任务修复范围）。
- 后端 focused：H2-C 4/4 + S1 credential 三件套 + H2-B runtime closure
  = 42/42 全绿。
- 单一 fresh-stack 全后端套件（`PW1R3_TEST_REDIS_URL` 已设，pw1r3 无红）：
  branch = 8 failed / 3651 passed / 69 skipped / 15 xfailed / 35 errors，
  对账 gap=0（3778 = 3651+8+69+15+35+0）。
- **差分归因（parent 对照，同主机/同 venv/同栈条件）**：PARENT
  `b2d28f32` = 8 failed / 3647 passed / 69 skipped / 15 xfailed / 35
  errors；**失败集与错误集与 branch 完全一致（diff 为空）**。本 delta
  引入零新增红。红集全部为 Alembic 临时数据库/迁移基础设施节点
  （s4g migration infra、i1_r4_r1 real-alembic、dc11t2 temp-db、
  dc11t4c、s1_r5 preflight、u1r1 sidebar smoke 等），属 Windows 宿主
  环境门控；权威 zero-red（3773/3710/48/15）属 Lubuntu 权威环境。
  本任务不声称本主机 zero-red。
- full-suite post-state（任务 DB）：4 wholesalers / 2 retailers / 31
  uuid schemas / 0 活跃 reset token。不声称 residue=0；已知 4/0/29
  测试卫生债务保持原状（属既有披露，非本任务新增）。
- 未运行、不声称权威 Playwright browser PASS；HC01-HC17 浏览器权威
  执行属后续独立门。

## 5. 质量门（Phase 5）

- py_compile（两后端文件）+ tsc（tsconfig.app.json）：通过。
- `git diff --check`（PARENT..HEAD）：干净。
- scoped pre-commit（12 文件，含 detect-secrets；测试文件内测密码按
  仓库惯例标注 `pragma: allowlist secret`）：Passed。
- 12 文件严格 UTF-8、无 BOM。
- GitNexus：本分支重建索引，`status` up-to-date；变更文件集 == 预期
  12 文件（精确 diff 复核，无 allowlist 外流程）。
- 未修改 authService.ts / 冻结 harness / migration / model / schema /
  dependency / lockfile。

## 6. 裁决

FINAL VERDICT:
**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_R1_CANDIDATE_READY_FOR_KILO_REVIEW**

CLAIM_CEILING：`CANDIDATE_READY_FOR_KILO_SOURCE_REVIEW`。
完成后 STOP：不启动权威 Playwright 旅程、不合并、不部署、不启动
PRICING/SKU；下一步仅为 Kilo bounded source/test-authenticity review。
