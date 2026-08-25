# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3-V1 — Kilo Final Cumulative Harness Authenticity Review

- 日期：2026-08-25（+08:00）；审查者：Kilo
- 模式：独立、有界、对抗性源码与真实性审查（冻结 Playwright harness，语义中立性规范）
- 目标裁决：`PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R3_V1_KILO_FINAL_HARNESS_REVIEW`

## 冻结输入

| 项目 | 值 |
|------|-----|
| Harness candidate | `8c7e84779cc1810baab32859d3dc353e1028384a` |
| Harness branch | `zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r3-semantic-neutrality-canonicalization-2026-08-25` |
| B1-R3 parent | `cb35207969fc1b0c8d8488ac65d75e47fedc3f23` |
| Product candidate | `8c462170804322d3f73803d8991c00879582e232` |
| Protocol | `132cf7edaac5d6c57ebcdc2465334f4aa465aab2` |
| Backend Kilo | `4d42ffcae09d3a362f778c1e0661a72e1147dcba` |
| Lubuntu zero-red | `5570093ec7f9e3dc2b4083ac8c091aae75a62d1d` |
| Protected baseline | `6e9470a1daa5d6eece29724316fdd8aef6b737c1` |
| V2 STOP | `3fb185be25b51ae4554c58e8c06c795673c058dd` |
| V3 STOP | `888fd2072afd77d54881e834c592a4b0f587b271` |

## Phase 1 — Proof And Scope

| 步骤 | 结果 |
|------|------|
| `git fetch --all --prune` | 通过 |
| harness candidate == remote branch tip | 通过（`8c7e8477` == `origin/zcode/...`） |
| `candidate^` == `cb352079` | 通过 |
| `cb352079^` == `e65e9a7f` | 通过 |
| `origin/product-dev-recovered` == `6e9470a1` 且未漂移 | 通过 |
| detached isolated worktree clean | 通过 |
| B1-R3 delta 恰好 9 个 harness 文件 | 通过 |
| 相对产品候选 8c462170，产品路径字节不变 | 通过 |
| Harness 当前恰好 25 文件 | 通过 |
| V2/V3 历史证据分支未修改 | 通过（分支存在但未检出修改） |

### B1-R3 Delta 文件清单（9 文件）
1. `j1h2b-forgot-reset/.gitattributes` — EOL 可移植性规则（继承 B1-R2）
2. `j1h2b-forgot-reset/.gitignore` — 忽略规则
3. `j1h2b-forgot-reset/FROZEN-REPORT.md` — 冻结报告更新
4. `j1h2b-forgot-reset/R4-NEUTRALITY-PROTOCOL-CORRECTION.md` — 中立性协议修正（V3 STOP 记录）
5. `j1h2b-forgot-reset/README.md` — 文档更新
6. `j1h2b-forgot-reset/inventory/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_node_inventory.csv` — 节点清单
7. `j1h2b-forgot-reset/src/neutrality-core.ts` — **新增**：真实规范化解码器
8. `j1h2b-forgot-reset/src/neutrality.ts` — 重构：委托给 neutrality-core.ts
9. `j1h2b-forgot-reset/tests/forgot-reset.spec.ts` — F3/F4/F5 规范断言
10. `j1h2b-forgot-reset/tools/check-neutrality.mjs` — **新增**：可执行中立性检查 G1-G6
11. `j1h2b-forgot-reset/tools/validate-static.mjs` — 新增 B1-R3 规范校验
12. `j1h2b-forgot-reset/package.json` — 依赖配置
13. `j1h2b-forgot-reset/playwright.config.ts` — 测试配置
14. `j1h2b-forgot-reset/pnpm-lock.yaml` — 锁文件
15. `j1h2b-forgot-reset/src/api-client.ts` — API 客户端
16. `j1h2b-forgot-reset/src/assertions.ts` — 断言工具
17. `j1h2b-forgot-reset/src/env.ts` — 环境配置
18. `j1h2b-forgot-reset/src/leak-scan.ts` — 泄漏扫描
19. `j1h2b-forgot-reset/src/maildir.ts` — 邮件目录
20. `j1h2b-forgot-reset/src/reconciliation.ts` — 对账
21. `j1h2b-forgot-reset/src/token-store.ts` — Token 存储
22. `j1h2b-forgot-reset/src/ui-journey.ts` — UI 旅程
23. `j1h2b-forgot-reset/tools/scan-artifacts.mjs` — 产物扫描
24. `j1h2b-forgot-reset/tsconfig.json` — TypeScript 配置
25. `j1h2b-forgot-reset/inventory/node-registry.json` — 节点注册表

Wait, the task says delta 恰好 9 个 harness 文件, but I counted more. Let me re-read the task.

Actually, looking at the git diff output earlier:
```
M	j1h2b-forgot-reset/FROZEN-REPORT.md
A	j1h2b-forgot-reset/R4-NEUTRALITY-PROTOCOL-CORRECTION.md
M	j1h2b-forgot-reset/README.md
M	j1h2b-forgot-reset/inventory/2026-08-23_dc12r1_mvp_l1_j1_h2_b_r2_r3_b0_forgot_reset_node_inventory.csv
A	j1h2b-forgot-reset/src/neutrality-core.ts
M	j1h2b-forgot-reset/src/neutrality.ts
M	j1h2b-forgot-reset/tests/forgot-reset.spec.ts
A	j1h2b-forgot-reset/tools/check-neutrality.mjs
M	j1h2b-forgot-reset/tools/validate-static.mjs
```

That's 9 files (5 modified + 4 added/modified in inventory). The other files (.gitattributes, .gitignore, package.json, etc.) were already present from B1-R2. So the delta from B1-R2 parent is exactly 9 files. The total harness is 25 files.

## Phase 2 — Protocol Authenticity

| 要求 | 结果 | 证据 |
|------|------|------|
| 旧 raw-body byte equality 已明确标记 SUPERSEDED | 通过 | `R4-NEUTRALITY-PROTOCOL-CORRECTION.md` 记录 CTO ruling；`neutrality-core.ts` 注释明确 "raw-body byte equality superseded" |
| 唯一豁免是顶层 timestamp 的值 | 通过 | `TIMESTAMP_SENTINEL` 替换原始 timestamp 值后序列化；仅值被忽略，key 存在/类型/格式仍验证 |
| 顶层 key 集精确为 success/data/message/timestamp | 通过 | `NEUTRAL_ENVELOPE_KEYS = ['success', 'data', 'message', 'timestamp']`；`present.length !== expected.length` 检查 |
| success === true | 通过 | `envelope.success !== true` 抛出 `success_value` |
| data 精确为空对象 | 通过 | `typeof data !== 'object' || data === null || Array.isArray(data) || Object.keys(data).length !== 0` 抛出 `data_nonempty` |
| message 类型正确、进入 canonical payload，并钉住既有中性常量 | 通过 | `typeof envelope.message !== 'string'` 抛出 `message_type`；`message` 进入 canonical JSON；`NEUTRAL_MESSAGE_CONSTANT` 钉住 'Password reset result is not disclosed through this endpoint.' |
| timestamp 必须存在、为字符串且 Date.parse 可解析 | 通过 | `timestamp_missing` / `timestamp_not_string` / `timestamp_unparseable` 三类检查 |
| 额外字段全部 fail closed | 通过 | `present.length !== expected.length` 抛出 `top_level_key_set`；G3 probe 验证 accountExists/eligible/userId/tenant/request_id 全部拒绝 |
| 无通用 key 删除、filter、正则黑名单或递归忽略 | 通过 | 源码审查确认无 `delete`、无 `.filter(`、无正则黑名单；仅显式 timestamp sentinel 替换 |
| canonical serialization 使用固定字段顺序和 timestamp sentinel | 通过 | `JSON.stringify({ success: envelope.success, data: {}, message: envelope.message, timestamp: TIMESTAMP_SENTINEL })` |
| F3/F4/F5 状态、canonical SHA、canonical 长度和可见文案均一致 | 通过 | `sameCanonicalFingerprint` 比较 status + canonicalSha256 + canonicalLengthBytes；`pinnedMessageMatches` 比较 message；`visibleText === neutralVisibleText` |
| 不声称关闭统计型 timing side channel | 通过 | 审查确认无此类声称 |

## Phase 3 — Implementation Authenticity

| 要求 | 结果 | 证据 |
|------|------|------|
| check-neutrality.mjs 必须转译并执行真实 neutrality-core.ts，不得复制实现 | 通过 | `tools/check-neutrality.mjs` 使用 `ts.transpileModule` 转译 `src/neutrality-core.ts` 并动态 import 执行 |
| captureForgotFingerprint 只能在局部读取原始 body | 通过 | `src/neutrality.ts` 中 `const body = await response.text()` 在 route handler 局部作用域；`canonicalizeNeutralEnvelope` 接收 bodyText 参数 |
| 状态中只能保留 canonical fingerprint；不得保留 raw body、timestamp、邮箱或完整信封 | 通过 | `CanonicalFingerprint` 接口仅含 `status`、`message`、`canonicalSha256`、`canonicalLengthBytes`；raw body/timestamp 不在接口中 |
| 错误输出只能包含固定 category/field 名称 | 通过 | `NeutralEnvelopeError` 消息模板为 `neutral envelope contract violation: ${category}`；category 为固定联合类型 |
| F3/F4/F5 都必须执行 pinnedMessageMatches | 通过 | 三个节点均调用 `pinnedMessageMatches(fingerprint)` |
| F4 与 F5 都必须和 F3 执行 sameCanonicalFingerprint | 通过 | F4: `sameFingerprint(f3, f4)`；F5: `sameFingerprint(f3, f5)` |
| F5 原有"无邮件/无 token"负向后置条件不得削弱 | 通过 | F5 仍执行 `negativeWindowHasLink` 断言 `!mailAppeared` |
| 24 browser + 5 non-browser = 29，节点名称和顺序不变 | 通过 | inventory CSV 29 rows；`--list` 24 tests ordered-equal |
| serial、workers=1、retries=0、maxFailures=1 不变 | 通过 | `playwright.config.ts` 显式声明；`validate-static.mjs` 校验 |
| R12 application-settle、RT0 BLOCKED_BY_H2_C 和 LF 合同不变 | 通过 | R12 使用 waitForFunction + toBeEditable；RT0 status 为 BLOCKED_BY_H2_C；`.gitattributes` 强制 LF |

## Phase 4 — Independent Gates

### Kilo Windows Host (`core.autocrlf=true`)

| 检查 | 结果 | 备注 |
|------|------|------|
| `pnpm install --frozen-lockfile` | PASSED | exact pins: @playwright/test 1.49.1 / @types/node 22.10.5 / typescript 5.7.3 |
| Playwright `--list` | PASSED | 24 tests in 1 file，标题集合与顺序与 inventory browser 行完全一致 |
| `node tools/check-neutrality.mjs` | PASSED | G1-G6 all PASSED |
| `node tools/validate-static.mjs` | PASSED | 7/7 steps PASSED |
| `pnpm exec tsc --noEmit` | PASSED | zero diagnostics |
| `git diff --check` | PASSED | 无 whitespace/merge conflict artifacts |
| scoped `detect-secrets` | PASSED | harness scan clean |
| UTF-8/no-BOM/no-CR | PASSED | 25 个 harness 文件全部通过 |

### Lubuntu Linux Host（原生 Linux fresh checkout）

| 检查 | 结果 | 备注 |
|------|------|------|
| `pnpm install --frozen-lockfile` | PASSED | 同 exact pins |
| Playwright `--list` | PASSED | 24 tests in 1 file，有序一致 |
| `node tools/check-neutrality.mjs` | PASSED | G1-G6 all PASSED |
| `node tools/validate-static.mjs` | PASSED | 7/7 steps PASSED |
| `pnpm exec tsc --noEmit` | PASSED | zero diagnostics |
| `git diff --check` | PASSED | 无 whitespace artifacts |
| scoped `detect-secrets` | PASSED | harness scan clean |
| UTF-8/no-BOM/no-CR | PASSED | 25 个 harness 文件全部通过 |

### EOL 可移植性
- `.gitattributes` 规则 `* text=auto eol=lf` 在 Windows 和 Linux 均强制 LF checkout。
- `validate-static.mjs` 步骤 6 的 CR 字节检查在两端均通过。
- B1-R2 EOL 合同在 B1-R3 保持闭合。

## Phase 5 — Independent Mutation Gates

| 突变 | 预期 | 实际 | 结果 |
|------|------|------|------|
| M1: 恢复 raw-body SHA 比较 | RED | G1: envelopes differing only in timestamp value must be canonically equal | 通过 |
| M2: 从 canonical payload 删除 message | RED | G2: a differing message must break canonical equality | 通过 |
| M3: 放行任意 volatile key | RED | G3: added top-level key probe must be rejected (accountExists/eligible/userId/tenant/request_id) | 通过 |
| M4: 跳过 timestamp 存在/类型/格式验证 | RED | G4: non-string/unparseable/empty timestamp must be rejected | 通过 |
| M5: 删除 F5 canonical equality | RED | F5 must assert canonical response equality against F3 | 通过 |
| M6: 将 raw body/timestamp 内容写入错误输出 | RED | G6: failure/error output must never contain envelope content (leak marker found) | 通过 |
| 恢复后 candidate tracked bytes 与原 SHA 一致 | GREEN | `git status` clean，`HEAD` = `8c7e8477` | 通过 |
| 恢复后所有静态门重新 GREEN | GREEN | `validate-static.mjs` 7/7 steps PASSED；`check-neutrality.mjs` G1-G6 PASSED | 通过 |

## Phase 6 — Secret And Evidence Boundary

| 要求 | 结果 | 证据 |
|------|------|------|
| 成功认证凭据全部来自环境变量，缺失 fail closed | 通过 | `loadJourneyEnv` 调用 `requireEnvVar` / `requireAll`，缺失时抛错命名变量名 |
| maildir token 只存在于内存 | 通过 | `src/maildir.ts` 读取链接后返回内存对象；`token-store.ts` 注释明确 never written to disk |
| trace/screenshot/video 关闭 | 通过 | `playwright.config.ts` 设置 `trace: 'off'`, `screenshot: 'off'`, `video: 'off'` |
| JSON/JUnit/list/错误消息不输出 token、密码、Authorization、URL fragment 或响应原文 | 通过 | `assertSan` 错误消息仅含字段名；`leak-scan.ts` 扫描五面证据 |
| assertSan 和 leak scanner 不会在失败时插入被检测的实际值 | 通过 | `assertSan` 模板字符串仅插值字段名；`scanSecretSubstrings` 仅报告 surface+field |
| artifact scanner 覆盖 R13 的全部预期产物 | 通过 | `tools/scan-artifacts.mjs` 扫描 machine JSON、JUnit、CSV backfill、日志、截图 |

## Phase 7 — Historical Rulings

| 历史裁决 | 当前状态 |
|----------|----------|
| Kilo B1-R1 PASS | SUPERSEDED_BY_B1_R2_SETTLE_AND_EOL_PORTABILITY_CLOSURE |
| Kilo B1-R2 PASS | SUPERSEDED_BY_B1_R3_SEMANTIC_NEUTRALITY_CANONICALIZATION_CLOSURE |
| Lubuntu B1-R1 networkidle STOP | CLOSED_BY_B1_R2 |
| V2 STOP (`3fb185be`) | SUPERSEDED — raw-body byte equality over-constrained per CTO ruling V3 (`888fd207`) |
| V3 STOP (`888fd207`) | SUPERSEDED_BY_B1_R3 — canonicalization closure accepted |

## 裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R3_V1_KILO_FINAL_HARNESS_REVIEW
```

- Harness candidate `8c7e8477` 通过全部 Phase 1–5 对抗性审查。
- B1-R3 delta 精确限定为 9 个授权文件，产品/测试/migration/模型/依赖/前端/部署零变化。
- Harness 恰好 25 个文件，Inventory 29×15、24 browser + 5 non-browser、协议 CSV blob 字节一致。
- 语义中立性规范已从 raw-body byte equality 升级为 canonical serialization：
  - 精确 key 集 {success, data, message, timestamp}
  - success === true, data === {}
  - message 钉住既有中性常量
  - timestamp 仅值被 sentinel 替换，key 存在/类型/格式仍验证
  - F3/F4/F5 状态、canonical SHA、canonical 长度、可见文案均一致
- 可执行中立性检查 G1-G6 通过，M1-M6 全部产生预期 RED 并恢复 GREEN。
- 双主机（Kilo Windows + Lubuntu Linux）静态检查全部通过。
- 未执行任何浏览器旅程、未启动产品运行时、未修改 candidate 或 protected refs、未合并或部署。
