# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R2 — Provisioning & Dynamic-Secret Scanner Reachability Closure

- 日期：2026-08-27（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1-R2（Provisioning and
  Dynamic-Secret Scanner Reachability Closure）
- 验证层级：V1_HARNESS_EXECUTABLE_CONTRACT_CORRECTION；CLAIM_CEILING：
  `HARNESS_FROZEN_AWAITING_KILO_RE_REVIEW`
- BASE：`bfd35b0e3c52e8b4854cb9e8af345e941d29e270`（远端一致）
- KILO_STOP：`26ed3fac9bfcf573e2a483e954d933228094509a`
  （= `origin/reports/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-b1-r1-v1-kilo-final-harness-re-review-2026-08-27`
  tip；4 findings：D=STOP（假前置成功）、I=STOP（扫描输入不可达）、
  H=WARNING（clearMemoryState 未调用）、SECRETS=WARNING（lockfile 3 处））
- PRODUCT_SOURCE：`bf20e8c9…`（产品/j1h2b/backend tests 零变化）
- 受保护基线 `2c20d58c…` 未漂移。
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-b1-r2-provisioning-scanner-reachability-2026-08-27`
- 授权范围：`j1h2c-retailer-recovery/**` + 本台账；未运行任何产品运行时
  或真实浏览器旅程；未修改全局 `.secrets.baseline` 或 lockfile 内容。

## 1. Kilo D — 正式供给闭合（逐项）

新增 `src/preconditions.ts`（可执行前置门，spec beforeAll 调用，全部在
浏览器节点之前，不计 browser PASS）：

1. **删除 409 放行**：`strictRegister` 只接受合同 2xx（200/201）；
   409/任何 4xx/5xx 一律 fail-closed（`strict_register_rejected:<status>`
   类别，只含状态码）。authoritative fresh runtime 使用全新未消费
   invitation，409 绝非可接受前置。
2. **完整官方生命周期**：register（严格 2xx）→ 从任务 maildir 读取 setup
   邮件（内存）→ `setup-credential` consume → 正式 login proof（2xx）。
   token 仅从 maildir 读入内存；零 SQL/ORM/debug/手写 hash。
3. **unverified retailer**：正式 register 后**明确停在验证/setup 之前**，
   并以 login-proof-must-fail 证明其未成为 established verified identity。
4. **W2**：launcher 合同（见 #9）供给；前置证明 W2 canonical code 类形
   有效且 **与 W1 不同**（`must_differ_from_w1`），且目标 retailer
   **不绑定 W2**（W2 门户 login 必须失败 `retailer_not_bound_to_w2_proof`）。
5. **unknown email**：规范化（trim+lowercase）后与全部正式身份
   （retailer、unverified）不同（`collides_with_provisioned_identity`）。
6. **launcher contract 可执行化**：`runPreconditions` 本身即机器可验证
   合同（env 缺失/形错/身份冲突/伪造 token 缺失全部 fail-closed），
   并由 validator [11] 静态锚定；README 叙述不是合同。
7. `--list` 无 env 仍可用（spec lazy env；前置仅在运行时执行）。
8. 运行前 maildir 快照（仅文件名）持久化为
   `artifacts/maildir-snapshot.json`，供 scanner 圈定本次运行。

## 2. Kilo I — 动态 secret 扫描可达性（逐项）

`tools/scan-artifacts.mjs` 重写动态输入派生（**弃用**子进程 env 交接）：

1. scanner 从任务 maildir、精确 retailer email 读取本次运行的 reset 邮件，
   内存解析全部 resetToken/setupToken。
2. 以 `artifacts/maildir-snapshot.json` 运行前快照圈定——只扫描本次
   新增邮件；历史任务 token 不进入 secret 集（fixture 证明）。
3. 本次全部邮件 token 逐一扫描全部 artifacts。
4. forged token 使用 `J1H2C_FORGED_RESET_TOKEN`：launcher 每次生成唯一
   值；spec HC15 使用 `env().forgedResetToken`；scanner 用同一值；
   缺失/过短/与任一邮件 token 相同均 fail-closed（复用=RED）。
5. 同时扫描 current/new password、Authorization 形状
   （Bearer/Basic 值模式）与 canonical w 禁止面。
6. secret 仅存在于 scanner 进程内存；无 secret 文件、无携带值的 CLI
   参数、无值输出。
7. 输出仅 file/surface/category。
8. maildir 不可读、本次新增 token 数为零、artifact 目录缺失、动态
   forged token 缺失/复用——全部 RED。
9. `package.json` 权威命令、README、launcher contract 一致
   （`--maildir-root $J1H2C_MAILDIR_ROOT --secrets-from-env`）。

## 3. Kilo H — 勘误与剩余合同

- **编辑前在 BASE 验证**：`clearMemoryState` 已 import（spec L53）且
  afterAll finally 已调用（L118）——警告在候选上不成立。记录
  **`KILO_H_WARNING_NOT_REPRODUCIBLE_AT_CANDIDATE`**，不做伪修复。
- reconciliation 剩余合同修正（harness 内）：
  1. 成功运行存在非 PASS 节点 ⇒ `assertComplete` RED（既有+fixture）。
  2. 新增 `NOT_RUN` 状态与 `markOutcomesAfterFailure(firstFailedNodeId)`：
     spec afterEach 捕获首个失败节点 id；到达但未通过=FAIL，停止点
     之后=NOT_RUN——不再混写。
  3. 首个失败不被 afterAll 掩盖：maxFailures=1 先停；afterAll 仅发布
     真实状态（publishArtifacts），发布错误独立surface。

## 4. Detect-secrets 处理

- raw scoped scan：`pnpm-lock.yaml` 共 7 处 Base64 High Entropy
  （行 24/29/32/37/42/47/52）——全部为 `integrity: sha512-…` pnpm
  依赖完整性哈希，**工具原始扫描 false positive**（Kilo 报告的 3 处
  为其子集）。
- 正式 baseline 模式：仓库 pre-commit `detect-secrets`（`--baseline
  .secrets.baseline`，且 `exclude: package.lock.json|pnpm-lock.yaml`）
  ——**PASS**。
- 未修改全局 `.secrets.baseline`、未在 lockfile 加绕过注释；
  本轮新增 fixture 字面量按仓库惯例 `pragma: allowlist secret`。
- 无需单独治理授权（正式门通过）。

## 5. 可执行 runtime-contract 扩展（真实导入当前模块）

新增/扩展 fixtures：严格 2xx register（409 禁绝——锚 + 无 409 分支）、
lifecycle 锚（setup consume + login proof）、W1==W2 拒绝、retailer-W2
绑定失败证明、unknown-email 规范化冲突拒绝、maildir 派生 fresh token
（clean→leak→RED）、历史 token 排除、forged token 复用 RED、forged
泄漏 artifact RED、缺动态输入 fail-closed RED、reconciliation
FAIL/NOT_RUN 区分与计数、clearMemoryState 调用点存在。

## 6. 变异门 M20–M27（全部 RED → SHA-256 恢复 → GREEN）

M20 409 放行；M21 跳过 verify/setup；M22 W1==W2 放行；M23 删 W2 绑定
失败证明；M24 邮件 token 不扫描；M25 forged token 不扫描；M26 缺
secret 输入放行；M27 移除 clearMemoryState。首轮 M22/25/26/27 NOT-RED
根因（文本锚被禁用分支满足/fixture 未覆盖语义）已如实记录并以
锚强化 + 新 fixtures 复验为确定性 RED；每项恢复与冻结快照逐字节一致。
既有 M1–M19 证据保留（B1/B1-R1 台账）。

## 7. 冻结门禁（全部通过）

`pnpm install --frozen-lockfile`；`--list` 15/1/有序；validate-static
**11/11**（新增 [11] D/I 锚）；check-neutrality G1–G6；
check-runtime-contracts（A/B/E/C/H/I + D/I-extra）；tsc；diff-check；
正式 detect-secrets baseline gate PASS + raw 分类记录；全文件
UTF-8/no-BOM/no-NUL/LF；GitNexus analyze/status up-to-date；
产品/j1h2b/backend tests 相对 PRODUCT_SOURCE 零变化；变异后 tree
无漂移（status clean）。

## 8. 裁决

VERDICT:
**STOP_AND_REPORT_CTO_AWAITING_KILO_H2C_HARNESS_RE_REVIEW**

CLAIM_CEILING：`HARNESS_FROZEN_AWAITING_KILO_RE_REVIEW`。
推送、local == remote、worktree clean（保留供 Kilo）。完成后 STOP，
不启动产品运行时。
