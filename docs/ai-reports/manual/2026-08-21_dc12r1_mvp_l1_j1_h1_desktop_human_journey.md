# DC-12R1-MVP-L1-J1-H1 Desktop Human Business Journey — 审计报告

- 日期：2026-08-21（+08:00）
- 产品 SHA（冻结）：`c5b66d26b83a0cc6170282de1e2fe281e448b2a8`（核验一致，工作区干净）
- 运行时：backend 127.0.0.1:8000（staging，真实 JWT）/ frontend 127.0.0.1:5173 / Alembic head `037_payment_declarations_schema`
- 操作者：真实人类用户（批发商 Persona A = jeff ltd / jeff05992582@126.com）
- 记录者：ZCode（观察/计时/证据采集；不点击、不代操作、不调 API）
- 环境偏差：任务书要求 Compose 项目；实际采用本地 venv + launcher（与 J1-R0 同方案），记 ENVIRONMENT_ONLY

---

## 总裁决

**STOP_AND_REPORT_CTO_WITH_REPRODUCIBLE_PRODUCT_BLOCKER**

权威人工旅程在 Step 5（邀请零售商）因 F-13 阻断；CTO 授权诊断性继续后，同一链路在邀请生成环节再次因 F-14 阻断。获客链路（批发商邀请零售商）**后端 API 完整、前端生产端未交付**，零售商侧旅程（Step 6–12）无法在任何受支持 UI 上开展。

---

## 第一部分：Authoritative Journey（Step 1–5，终止于 F-13）

| Step | 目标 | 结果 | 关键发现 |
|---|---|---|---|
| 1 | 创建批发商账户 | 完成（含摩擦） | F-01 国家无下拉；F-02 两处转场无指引；F-03 注册时无密码与用户期望冲突 |
| 2 | 邮箱验证 + 设置凭据 | 完成（含摩擦） | F-02（验证页不告知第二封邮件）；F-04 小眼睛正向反馈 |
| 2-extra | （旅程外）忘记密码 | **BLOCKER** | F-05 静默失效（见下） |
| 3 | 登录并判断下一步 | 完成（含摩擦） | F-06 无新手指引；F-07 显示租户编码非公司名；F-08 无中文/STOCK 误译；F-09 国家 UG 财务货币 KES |
| 4 | 创建第一个商品 | 完成（含摩擦） | F-11 导入体验断裂；F-12 字段结构待三层方案 |
| 5 | 让零售商能够采购 | **BLOCKER 停止** | F-13 邀请入口不可达 |

### F-05（BLOCKER）：忘记密码流程静默失效

三次 UI 提交均返回中性成功，`password_reset_tokens` 恒为 0；应用外重放同一服务代码（同库同 env）`issued=True` 可提交。证据指向应用内租户会话上下文（RLS/GUC）使 wholesalers 扫描返回空 + 永久中性 200 策略完全掩盖故障。真实用户将永远等不到重置邮件且无任何错误线索。

### F-13（BLOCKER，旅程终止点）：邀请入口经导航不可达

`InvitePage` 存在但为孤儿页面：侧栏（`Sidebar.tsx:32-38`）无此项，Customers 页无邀请按钮。操作者全程未找到入口。

### F-09（HIGH_FRICTION，财务正确性）：国家不联动货币

注册国家 UG（乌干达），财务模块货币 KES（肯尼亚先令）。国家→默认货币映射缺失；未来需支持例外结算货币（如 USD）。将直接影响未走到的 Step 8/11/12（定价、付款申报、财务记录）。

完整发现清单（F-01..F-14）见 `2026-08-21_dc12r1_mvp_l1_j1_h1_friction_findings.csv`；逐步事件含时间戳/耗时/客观证据见 `2026-08-21_dc12r1_mvp_l1_j1_h1_journey_events.csv`。

---

## 第二部分：CTO_AUTHORIZED_DIAGNOSTIC_CONTINUATION_AFTER_F13

授权与条款全文见 `evidence/j1-h1/operator_notes.md`。执行结果：

- 唯一授权桥接（操作者手动输入 `/invite`）执行后 **404**：路由实为 `/invite/:code`（`AppRouter.tsx:107`），该页为零售商消费端。
- 深入核查发现 **F-14（BLOCKER，二次停止点）**：后端邀请 API 完整（`api/v1/invitations.py`：创建/lookup/撤销），但前端零处调用 `POST /invitations`；Customers 页空态文案承诺 "invitation link" 而系统无任何 UI 能生成它。
- 依 CTO 条款 4（禁止代理调 API/预置邀请）与条款 6（不得新增第二桥接），诊断旅程在此停止。Step 6–12 未执行。

**F-13 + F-14 合并判定**：零售商获客链路为"后端就绪、前端生产端整体未交付"。

---

## 发现统计

| 分类 | 数量 | 编号 |
|---|---|---|
| BLOCKER | 3 | F-05（密码找回静默失效）、F-13（邀请入口不可达）、F-14（邀请生成无 UI） |
| HIGH_FRICTION | 4 | F-02（转场无指引）、F-06（无新手指引）、F-09（货币不联动国家）、F-11（导入体验断裂） |
| CAPABILITY_GAP | 3 | F-08（i18n）、F-10（员工管理缺失，侧栏 Team 被注释）、F-12（商品三层结构待 CTO 方案） |
| POLISH | 4 | F-01（国家无下拉）、F-03（注册时设密码期望）、F-04（正向）、F-07（租户编码替代公司名） |
| ENVIRONMENT_ONLY | 2 | 预检迁移缺失（已修复，见 operator_notes）、本地 maildir 替代 SMTP |

## CTO 已裁定的修复范围控制（转录）

- **F-13 MVP 必修**：侧栏或 Customers 页增加清晰 "Invite retailer" 入口 + 空态 CTA + 导航测试。
- **二维码邀请**：高价值增强，不替代最小入口修复；实施前需单独定义 token 生命周期、防重放、批发商绑定、过期与泄漏合同。
- F-05 修复时须同时解决"中性 200 策略掩盖内部故障"的可观测性问题（内部应告警/日志，外部保持中性）。

## 证据文件

- `evidence/j1-h1/runtime_preflight.md` — 预检与 ENVIRONMENT 缺陷修复记录
- `evidence/j1-h1/operator_notes.md` — 逐步观察记录 + CTO 授权条款
- `evidence/j1-h1/screenshots/` — （占位；本会话截图由操作者终端粘贴件承载，见事件表 screenshot 引用）
- `evidence/j1-h1/manifest_sha256.txt` — 交付物哈希清单
- 密码/token/SECRET 均未写入任何交付物；邮件 token 在转录中已脱敏
