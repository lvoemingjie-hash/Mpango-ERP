# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R2-V1 — LUBUNTU Final Harness Authenticity & EOL Portability Review

- **日期:** 2026-08-24（+08:00）
- **执行方:** OpenCode — 原生 Lubuntu 独立运行时审查（LUBUNTU 交付侧；Kilo 的 Windows/core.autocrlf=true 侧为独立执行方交付，不在本报告范围）
- **模式:** 双主机最终 Harness 真实性与 EOL 可移植性审查的 Lubuntu 半边。未启动 backend/frontend/PostgreSQL/Redis；**未执行任何权威浏览器旅程**（仅 `--list` 与纯静态检查）；未修改候选；未合并、未部署。

## 最终裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R2_V1_LUBUNTU_FINAL_HARNESS_REVIEW
```

## 历史裁决确认（Lubuntu 义务）

**本执行方 B1-R1 的 networkidle STOP（缺陷 F1，分支 `reports/...b1-r1-v1-lubuntu-native-harness-review-2026-08-24` @ `ed8b0082`）已由 B1-R2 关闭。** 证据：
- `tests/forgot-reset.spec.ts` R12 的 `waitForLoadState('networkidle', 15s)` 已删除，替换为有界真实应用条件等待（15s `waitForFunction`：`pathname === '/reset-password'` && `location.hash === ''`）+ `expect(#newPassword).toBeEditable()`，满足后立即执行 leak scan；
- validator 将 `networkidle` 列为全域禁用标记（M1 变异 RED 证明强制有效）；
- 修复方向与本执行方 B1-R1 报告的建议一致（有界真实应用条件替代 networkidle）。宿主形态依赖消除：settle 条件不再依赖网络静默，Vite dev HMR WebSocket 存在与否不影响判定。

## Phase 1 — 证明与范围（全 PASS）

| 检查 | 结果 |
|---|---|
| `git fetch --all --prune` 后 candidate `cb35207969fc1b0c8d8488ac65d75e47fedc3f23` == 远端 `origin/zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r2-app-settle-eol-portability-2026-08-24` tip | PASS |
| `candidate^ == e65e9a7f61c78906c2c5874d6589d4bada23942c` | PASS |
| B1-R2 delta 恰好 5 个授权文件 | PASS — A `.gitattributes`；M `tests/forgot-reset.spec.ts`、`tools/validate-static.mjs`、`README.md`、`FROZEN-REPORT.md`；无第六文件 |
| 相对产品候选 `8c462170`，j1h2b-forgot-reset/ 之外所有路径字节不变 | PASS — 0 个产品路径出现在 diff |
| Harness 当前恰好 22 个文件 | PASS — git ls-tree 计数 22（21 + .gitattributes） |
| detached isolated worktree（`/home/ivy/MPANGO/dc12r1-b1r2-harness-wt`）porcelain 0 | PASS |

## Phase 2 — 指令 11 项核验（全 PASS）

1. candidate == 远端 tip — PASS。
2. parent == `e65e9a7f` — PASS。
3. delta 恰 5 授权文件 — PASS（见上表）。
4. 产品路径零变化；harness 22 文件 — PASS。
5. R12 不含 networkidle / waitForTimeout / 固定 sleep — PASS（R12 区域 0 命中；全域 waitForTimeout 禁令保持；grep 命中仅为 M1 的 `test.setTimeout`、api-client AbortController 30s 定时器与 maildir 轮询间隔——均非 R12 settle 等待）。
6. R12 有界等待同时证明 pathname 精确、hash 为空、`#newPassword` 可见且 editable（`toBeEditable` 隐含可见可交互），条件满足后立即 leak scan（secrets 构造与 Surface 1-4 紧随，无中间等待）— PASS。
7. `.gitattributes` 有效规则恰为 `* text=auto eol=lf`，无 `eol=crlf` — PASS。
8. 单一 spec（tests/ 仅 forgot-reset.spec.ts）、单一外层 serial describe、`maxFailures:1`、`workers:1`、`retries:0`、`fullyParallel:false` — PASS（validator comment-stripped 强制）。
9. `--list` 精确 24 节点且有序相等 CSV browser 行；总对账 24 browser + 5 non-browser = 29 — PASS。
10. RT0 仍为 `BLOCKED_BY_H2_C`、无 API 绕过 — PASS（inventory/node-registry.json 在 delta 中零改动；validator + reconciliation.ts 不变量强制）。
11. 既有凭据、maildir、token、日志与证据泄漏边界未削弱 — PASS（B1-R2 delta 未触碰 `src/` 全部边界实现、`tools/scan-artifacts.mjs`、`playwright.config.ts`、`inventory/`；spec 改动仅限 R12 settle 块，四表面 leak scan 原样）。

## Lubuntu 原生 Linux 实际门禁（全 PASS；fresh checkout）

fresh detached checkout（`core.autocrlf` 未设置，Linux 原生默认；porcelain 0）：

| 门 | 结果 |
|---|---|
| `pnpm install --frozen-lockfile` | PASS（lockfile 零漂移；@playwright/test 1.49.1 exact-pin） |
| `pnpm exec playwright test --list` | PASS — Total: 24 tests in 1 file；与 CSV browser 行有序相等 |
| `node tools/validate-static.mjs` | PASS — **STATIC GATE PASSED 6/6**（CSV 29×15、registry、有序 --list、journey 契约含 R12 app-settle、EOL 契约、UTF-8/no-BOM/no-CR over 22 files） |
| `pnpm exec tsc --noEmit` | PASS（exit 0） |
| 独立字节复核（非复用 validator） | PASS — 22 文件：BOM 0、CR 字节 0（LF-only）、严格 UTF-8 全过 |
| `git diff --check e65e9a7f..cb352079` | PASS（clean） |
| scoped detect-secrets（tests/src/tools/config/inventory/docs/.gitattributes/.gitignore） | PASS — 0 findings |

## 变异门 M1-M5（独立执行；每项 RED → 字节还原）

| 突变 | 结果（validator） |
|---|---|
| M1 恢复 networkidle（R12 追加 waitForLoadState） | **RED** — `forbidden marker networkidle found in tests/forgot-reset.spec.ts` |
| M2 删除 pathname/hash 条件（整块 waitForFunction 移除） | **RED** — `R12 must wait for the application-settle pathname condition` + `empty-hash condition` |
| M3 删除 #newPassword 可交互条件（toBeEditable 行移除） | **RED** — `R12 must wait for the reset form #newPassword to be visible and interactable` |
| M4 删除 .gitattributes | **RED** — `must exist (EOL portability contract)` |
| M5 eol=lf 改 eol=crlf | **RED** — `must contain the rule '* text=auto eol=lf'` + `must not contain any eol=crlf rule` |

恢复后：validator **6/6 GREEN**、`--list` 24 GREEN、worktree porcelain **0**、`git diff HEAD` 空、harness 子树 blob 清单 SHA-256 与候选提交逐字节一致（`cfc34889ae093591d855df8d3b01fc9eaf6370da26b8f15d040f530113513dcf` 两处相等）——**候选 blob 未漂移**。

## 附注与披露

- 本报告仅为 LUBUNTU 半边；Windows（core.autrcrlf=true fresh checkout）侧门禁由 Kilo 独立执行并在其分支交付——**本报告不代其声明任何 Windows 侧结果**。
- 未声称执行过权威浏览器旅程；未启动任何产品运行时。
- 未修改候选任何字节；受保护 refs 未触碰。
- 本轮 GitNexus 不在指令门禁清单内，未运行。
- 下一步（CTO 批准后）：独立 fresh-runtime 单次权威浏览器执行。
