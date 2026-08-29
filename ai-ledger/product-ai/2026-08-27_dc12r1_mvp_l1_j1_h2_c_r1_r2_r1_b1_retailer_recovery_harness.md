# DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1 — Retailer Recovery Browser Harness 工程

- 日期：2026-08-27（+08:00）；执行者：Zcode
- 任务：DC-12R1-MVP-L1-J1-H2-C-R1-R2-R1-B1（Retailer Recovery Browser
  Harness Engineering）
- 验证层级：V1_HARNESS_SOURCE_AND_STATIC_AUTHENTICITY；CLAIM_CEILING：
  `HARNESS_FROZEN_AWAITING_KILO_REVIEW`
- BASE：`bf20e8c9eae620fcf101ded672dfb0afeab937cb`（远端一致）
- KILO_REVIEW（R2-R1 bounded delta review，PASS）：
  `f5fdf187fab88f628a6b2f3aca80d03d3be60054`
- LUBUNTU_E1（E1 manifest self-exclusion fix）：
  `6a62fb19b2973f9565e7bfe93ada133903d693cf`
- 受保护基线：`origin/product-dev-recovered@2c20d58c…`（未漂移）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-r1-r2-r1-b1-retailer-recovery-browser-harness-2026-08-27`
- 授权范围：新增独立目录 `j1h2c-retailer-recovery/**` + 本台账。

## 1. Phase 1 — 证明与清单（全部通过）

- 四个冻结引用逐一验证（本地 == 远端）：BASE `bf20e8c9`、KILO_REVIEW
  `f5fdf187`、LUBUNTU_E1 `6a62fb19`、受保护基线 `2c20d58c`。
- 源 inventory 逐字节复制到 `j1h2c-retailer-recovery/inventory/`：
  git blob `caa5340299…` 与 SHA-256 `70446a0a…faf243c8` 双双相等。
- 严格解析：17 行 × 15 列；HC01–HC17 有序唯一。
- 执行分类真值：15 个 BROWSER（HC01–HC10、HC12–HC16）+ 2 个 STATIC
  （HC11、HC17；CSV 字段为 `STATIC`，与任务的 "STATIC_RUNTIME" 指同一
  节点集 —— 字段逐字节保留，不改写）。HC11/HC17 在 reconciliation 中
  单独记账（`PENDING_RUNTIME_CHECK`），禁止伪报为浏览器 PASS。
- `playwright test --list`：恰 15 项 / 1 文件，与 browser 行有序相等。

## 2. Phase 2-3 — 独立 harness 与运行时设计合同（已实现，未运行）

- 独立目录（参考 j1h2b 但零运行时依赖）：`.gitattributes`（`* text=auto
  eol=lf`）、`package.json`（@playwright/test 1.49.1 / @types/node
  22.10.5 / typescript 5.7.3 精确固定）+ `pnpm-lock.yaml`（lockfile v9）、
  `playwright.config.ts`（fullyParallel=false、workers=1、retries=0、
  maxFailures=1、trace/screenshot/video off、不可解析 fallback host
  `http://j1h2c.invalid.frozen-harness.local`）、`tsconfig.json`、
  `README.md`、`FROZEN-REPORT.md`、`inventory/node-registry.json`、
  单一 serial spec `tests/recovery.spec.ts`、`src/**`（env/neutrality-core/
  neutrality/maildir/token-store/leak-scan/api-client/ui-journey/
  reconciliation/assertions）、`tools/**`（validate-static / check-neutrality
  / scan-artifacts）。
- 运行时设计合同要点：凭据仅来自 `J1H2C_*` env（run-time 读取，--list
  零 env 可用，缺变量 fail-closed 只报变量名）；供给仅走正式 API 生命周期
  （无 SQL/ORM/debug/手写哈希）；旅程动作全部经真实渲染 UI；maildir
  reset token 仅单进程内存；HC07–HC10 仅存 canonical fingerprint
  （精确键集 + 固定 message + timestamp 可解析后 sentinel 替换，raw body
  即刻释放）；HC06 双击恰一次 POST + maildir 只读后置证明唯一签发；
  HC02/HC05 零 recovery POST；HC11/HC17 从 HC07 邮件验证（fragment-only
  resetToken、公共 w、DB canonical 大写 w —— HC07 以小写 URL 代码导航）；
  HC12 扫描 URL/query/storage/console/network metadata；HC13 canonical
  门户返回（禁 `/login`）；HC14 真实有效 token 去 w 构造 legacy 链接、
  成功后仅中性指引；HC15 运行时伪造 token、失败信息不含 token 值；
  HC04/HC16 390px 模拟视口（明确非真机）。

## 3. Phase 5 — 静态验证器与变异门（M1–M10 全 RED + 字节恢复）

`validate-static.mjs` 9 步检查：inventory 形状、registry 交叉核对、
--list 15 项有序、单 spec/serial/fail-stop、禁用标记、EOL/编码、secret
边界、15+2 对账 gap=0、HC01–HC17 合同锚点。

| 变异 | 内容 | RED | 恢复 |
|---|---|---|---|
| M1 | 删除 maxFailures=1 | ✓ | SHA-256 一致 |
| M2 | 删除 serial mode | ✓ | SHA-256 一致 |
| M3 | 添加第二 spec 节点 | ✓ | SHA-256 一致 |
| M4 | 调换节点顺序 | ✓ | SHA-256 一致 |
| M5 | 弱化 canonical message 检查 | ✓（check-neutrality） | SHA-256 一致 |
| M6 | 允许 HC02/HC05 发 POST（删零调用锚） | ✓ | SHA-256 一致 |
| M7 | 削弱 token/w 泄漏边界（删 assertNoSecretLeak） | ✓ | SHA-256 一致 |
| M8 | 删除 HC13 canonical portal（删 expectPortalReturnCta） | ✓ | SHA-256 一致 |
| M9 | 弱化 HC14 legacy（删 expectLegacyGuidanceOnly） | ✓ | SHA-256 一致 |
| M10 | 删除 HC17 DB canonical 证明 | ✓ | SHA-256 一致 |

真实性问题（如实记录）：M2 首轮"NOT-RED"根因是 validator 的 serial
检查字符串在 spec docstring 注释中也有匹配（反引号、无分号）——已收紧
为冻结代码行（带分号）后确定性 RED；M6–M9 首轮"NOT-RED"根因是锚点
字符串在 import/docstring 中也存在且替换仅命中第一处——改为 replace-all
（import+调用同删）后确定性 RED。变异仅为 harness 静态真实性证据，
不声称产品运行时 PASS。

## 4. Phase 6 — 静态门禁（全部通过）

- `pnpm install --frozen-lockfile`：PASS（lockfile v9 精确固定）。
- `playwright test --list`：15 tests / 1 file，与 browser 行有序相等。
- `validate:static`：9/9 PASS。
- `check:neutrality`（可执行 G1–G6，真实转译 canonicalizer）：PASS。
- `tsc --noEmit`：PASS。
- `git diff --check`：干净。
- scoped pre-commit + detect-secrets：PASS（fixture 标记按仓库惯例
  `pragma: allowlist secret`）。
- 全文件严格 UTF-8 / 无 BOM / 无 NUL / LF（无 CR）：PASS。
- GitNexus analyze/status：本分支索引 up-to-date。
- M1–M10 恢复后全部候选 blob 与冻结快照 SHA-256 相等。
- 产品树（backend/frontend/docs/ai-ledger）与 `j1h2b-forgot-reset/**`
  相对 BASE 字节不变（`git diff --name-only` 为空）。

## 5. 如实披露与界限

- 未执行真实 Playwright 旅程；HC01–HC17 保持 PENDING_AUTHORITATIVE_RUN /
  PENDING_RUNTIME_CHECK（node-registry.json 无任何预写结果或 evidence
  SHA）。
- 未启动 backend/frontend/PG/Redis；无任何运行时 PASS 声明。
- 390px 检查为模拟视口，非真机证明。
- harness 冻结配置完全满足：无 skip/fixme/only、无 waitForTimeout/固定
  sleep/networkidle、证据零泄漏。

## 6. 裁决

VERDICT:
**STOP_AND_REPORT_CTO_AWAITING_KILO_H2C_HARNESS_REVIEW**

CLAIM_CEILING：`HARNESS_FROZEN_AWAITING_KILO_REVIEW`。
已提交并推送（local == remote 验证），worktree clean 且**保留**供 Kilo
审查；未启动任何产品运行时。完成后 STOP，等待 CTO 下发下一步。
