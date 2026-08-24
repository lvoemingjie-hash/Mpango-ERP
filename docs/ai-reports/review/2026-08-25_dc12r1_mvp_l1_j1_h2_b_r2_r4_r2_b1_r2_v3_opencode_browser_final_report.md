# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R2-V3 — OpenCode 浏览器终验报告（供给输入修正版）

- 任务代号: DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R2-V3 (opencode-browser-final)
- 日期: 2026-08-25（运行 UTC 2026-08-24T16:23–16:24Z）
- 执行方: OpenCode (ZCode)
- **裁决: `STOP_AND_REPORT_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R2_V3_OPENCODE_BROWSER_FINAL`**
  （未达成 `PASS_FOR_CTO_..._V3`。权威运行 **7 passed / 1 failed (F4) / 16 did not
  run**。V2 的供给输入缺陷已修复并验证；本次 F4 首红是**产品公共信封非确定性**
  发现：forgot-password 响应体携带逐请求 `timestamp` 字段，F3/F4 body 字节恒等
  在当前产品面上不可满足——违反冻结协议 CSV 的「同状态码/响应体」三重不可区分
  合同。按协议首红即停、零重跑、零数据修改。）

## 0. 冻结引用（运行前后均未变；V2 分支保持不变）

| 引用 | SHA |
|---|---|
| PRODUCT_SOURCE | `8c462170804322d3f73803d8991c00879582e232` |
| HARNESS | `cb35207969fc1b0c8d8488ac65d75e47fedc3f23` |
| V2_STOP_EVIDENCE | `3fb185be25b51ae4554c58e8c06c795673c058dd`（远端 tip 逐字复核一致；未修改/重写/force-push） |
| KILO_HARNESS_REVIEW | `1082f6177af69ce57c1951e07009d0a13f0e2400` |
| LUBUNTU_HARNESS_REVIEW | `9066e1171f55177a2362788ac22788a76d68d066` |
| BACKEND_ZERO_RED | `5570093ec7f9e3dc2b4083ac8c091aae75a62d1d` |
| PROTECTED_BASELINE | `6e9470a1daa5d6eece29724316fdd8aef6b737c1` |

## 1–4. 各阶段门禁（全部 PASS，明细见 evidence/preflight.md）

- **Phase 1 证明门**: fetch 后 detached worktree 精确位于 HARNESS；产品路径与
  PRODUCT_SOURCE 字节一致（22 个差异文件全部在 `j1h2b-forgot-reset/`，外部 0）；
  harness 22 文件、工作树 clean；全部冻结 refs 未漂移（含 V2 分支 == 3fb185be）。
- **Phase 2 供给输入预检（V2 缺陷的修复面）**: 6 个全新唯一邮箱使用非
  special-use 真实 TLD 子域 `mail.j1h2b-v3-task.dev`；在启动 Playwright 之前用
  候选后端实际安装版本（pydantic 2.12.5 + `schemas.auth_signup.SignupRequest`）
  **离线验证**：`validated_email_count=6, all_valid=true,
  special_use_domain_count=0`（identity-summary.json；未记录任何完整邮箱）。
  同一探针确认 `.invalid/.test/.local/localhost` 被正确拒绝（复现并关闭 V2 根因
  模型）。env 文件生成即带正确引用（V2 调用#1 缺陷在源头消除）；22 个 J1H2B_*
  变量逐一证明非空（仅变量名+布尔，env-preflight-variables.txt，MISSING=0）。
- **Phase 3 全新运行时**: 独占 `j1h2b-v3-pg16`/`j1h2b-v3-redis7`/两卷/一网，
  空库 → Alembic 唯一 head 037；backend `main:app` + `MPANGO_ENV=staging` + 真实
  JWT（全新随机 SECRET_KEY，未打印未提交）；frontend **Vite dev host（HMR）**；
  全新 maildir；不复用 V2 任何数据/身份/容器/目录；端口 8000/5173/55433/56380
  预检空闲、仅绑回环。
- **Phase 4 冻结前置门**: install（精确锁定）/ list（24 tests、1 spec、CSV 序）/
  validate-static 6/6 / tsc 零诊断 / diff-check 干净 / detect-secrets 源码 0 发现；
  健康三检查 200。PB-1 复核：零售商发现层仍缺失 → **RT0 维持 BLOCKED_BY_H2_C**。

## 5. 唯一权威运行（完整命令恰一次，无预跑/grep/shard/retry）

UTC 2026-08-24T16:23Z 启动，`Running 24 tests using 1 worker`：

- **7 passed**: F1-D/F1-T/F1-M、F2-D/F2-T/F2-M（Vite dev host 三视口，含
  390px 无溢出）、**F3（6.4s）**——V2 供给修复生效：A1 经正式生命周期供给成功
  （signup 202 → maildir 验证链接 → verify-email 200 → setup 链接 →
  setup-credential 200 → login），X 经正式创建+软删除供给，随后**浏览器旅程动作
  全部执行**（/forgot-password 渲染表单提交 A1 邮箱、固定中性文案断言、
  POST /auth/forgot-password 200 指纹采集）。maildir 于运行结束含 3 封任务邮件
  （verify、owner-setup、reset）。
- **1 failed: F4（541ms）** — 枚举防护核心节点。净化断言报文：
  `F4: response differs from F3 (first differing field: bodySha256)`。
  即未知邮箱与已注册邮箱的 forgot 响应**状态码相同（均 200）、body 长度相同、
  但 body 字节不同**。
- **16 did not run**（maxFailures:1 首红即停；stats: expected 7 / unexpected 1 /
  skipped 16 / flaky 0 / interrupted 0；总时长 11.3s）。

### 根因（产品面发现，非启动器缺陷）

公共信封 `ForgotPasswordResponse`（backend/schemas/auth_signup.py:168-176）含
`timestamp: datetime = Field(default_factory=datetime.utcnow)`，端点
（backend/api/v1/auth.py:826-829）每次请求以 `datetime.utcnow()` 构造响应。
**离线代码级证明**（evidence/f4-envelope-nondeterminism-proof.txt）：构造两个
语义完全相同的中性信封，`byte_identical=False`，唯一差异字段 `['timestamp']`，
其余字段全等。因此：

1. F3 vs F4 的 sha256(body) 恒等断言对**任何**调用方都不可满足——即使两次请求
   都是 F3（同邮箱同结果）body 也不相同；
2. 该差异与账户存在性**无相关性**（不构成枚举信号本身），但冻结协议 CSV F4 行
   要求「与 F3 同状态码/**响应体**/可见文案三重不可区分」，且协议 §5.7 STOP
   条件为「公开响应出现枚举差异（F3 vs F4 **任何可观测不同**）」——逐请求时间戳
   就是可观测不同，合同违约成立。

分类：**PRODUCT_ENVELOPE_NON_DETERMINISM**（产品 vs 冻结协议合同违约；安全影响
评估为低——字段与账户存在性无关——但合同层面 F4 不可通过是结构性事实）。
harness 行为正确（忠实实现冻结断言且净化报文）；启动器输入已全部预检通过。

### 协议遵守声明

首红即停：未修改任何产品/harness/协议/锁文件，未重置数据，未重跑（本任务是
V3 的唯一一次完整运行；与 V2 两次调用互不掩盖，V2 证据原样保留于 3fb185be）。
R1–R12、M1 未达；R12 的 B1-R2 app-settle 条件仍未经浏览器验证（待 F4 修复后
的后续授权运行验证）。

## 6. 对账与秘密边界

- 原始 JSON/JUnit/console：evidence/authoritative-run/（7/1/16，11.3s）。
- 24 行 CSV + test-list + reconciliation.json：**29 节点 gap=0**（24 browser +
  5 non-browser）。非浏览器：R13 已执行 **PASS**（3 产物文件零泄漏，含
  --secrets-from-env 对 8 个运行密码的逐字节匹配）；F6 部分行使（F3 供给链的
  verify/setup 链接获取已发生；reset 链接获取因 F4 停止未达，不虚报 PASS）；
  R6/M2 维持 BACKEND_PRE_GATE_ONLY（引用 5570093e）；RT0 维持 BLOCKED_BY_H2_C。
- failure_set.json：F4 failed + 16 skipped 全列。
- 供给预检证据：identity-summary.json（仅计数/布尔）、
  env-preflight-variables.txt（仅变量名+布尔）、preflight.md。
- 证据目录带值泄漏扫描（8 密码+SECRET_KEY+REPORTING_USER_PASSWORD 匹配 +
  Bearer/resetToken/完整邮箱结构扫描）：**0 发现**；未提交任何邮箱全文、密码、
  JWT、Authorization、token、maildir 原文或环境文件。
- committed-blob manifest：22 个 harness 文件 blob SHA-1 + 内容 SHA-256。
- 清理闭包：evidence/cleanup.md（进程/端口/容器/卷/网络/maildir/凭据/日志/
  venv/worktree 全清；冻结 refs 与 V2 分支不变）。

## 7. 裁决与下一步

**`STOP_AND_REPORT_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R2_V3_OPENCODE_BROWSER_FINAL`**

- 真实结果：7/24 浏览器节点通过（含 F3 完整供给链+旅程动作，证明 V2 修复有效）；
  F4 揭示**产品信封非确定性**（逐请求 timestamp）使冻结中性合同结构性不可满足。
- 供 CTO 决策的处置选项（均需新授权，本任务不执行）：
  1. **产品修复路径**：从公共 forgot-password（及同族中性信封）移除逐请求
     `timestamp` 或改为确定性值 → 属产品变更，走正常缺陷修复+审查+受控合并，
     然后以 V4 新协议授权重跑；
  2. **协议豁免路径**：重新冻结协议/harness，将 F4 比较收窄为「剔除非语义
     per-request 字段后的语义等价」——需明确论证不弱化枚举防护，并重走
     Kilo harness 审查；
  3. 任一路径下 F1–F3 的本次 PASS 仅为历史证据，不跨任务复用。
- 即使后续全绿：不合并、不部署、不启动 H2-C；下一步仅为 Kilo 对 V3 机器证据
  的最终审查，再由 CTO 决定受控合并。RT0/PB-1 仍待 H2-C。
