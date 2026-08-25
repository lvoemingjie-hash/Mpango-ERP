# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2-B1-R3-V1 — LUBUNTU Final Semantic Neutrality Harness Authenticity Review

- **日期:** 2026-08-25（+08:00）
- **执行方:** OpenCode — 原生 Lubuntu 独立运行时审查（LUBUNTU 交付侧；Kilo 的 Windows/core.autocrlf=true 侧为独立执行方交付，不在本报告范围）
- **模式:** 双主机最终语义中性 Harness 真实性审查的 Lubuntu 半边。未启动 backend/frontend/PostgreSQL/Redis；**未执行任何权威浏览器旅程**（仅 `--list`、可执行中性检查与静态门禁）；未修改候选；未合并、未部署、未启动 H2-C。

## 最终裁决

```
PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_B_R2_R4_R2_B1_R3_V1_LUBUNTU_FINAL_HARNESS_REVIEW
```

## Phase 1 — 证明门（全 PASS）

| 检查 | 结果 |
|---|---|
| `git fetch --all --prune` | EXIT 0 |
| candidate `8c7e84779cc1810baab32859d3dc353e1028384a` == `origin/zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-b1-r3-semantic-neutrality-canonicalization-2026-08-25` tip | PASS |
| `candidate^ == cb35207969fc1b0c8d8488ac65d75e47fedc3f23` | PASS |
| delta 恰好 9 个 harness 文件 | PASS — M `FROZEN-REPORT.md`/`README.md`/`inventory/…node_inventory.csv`/`src/neutrality.ts`/`tests/forgot-reset.spec.ts`/`tools/validate-static.mjs`；A `R4-NEUTRALITY-PROTOCOL-CORRECTION.md`/`src/neutrality-core.ts`/`tools/check-neutrality.mjs`；无第十文件 |
| 相对 PRODUCT_SOURCE `8c462170`，backend/**、frontend/**、migration、依赖、部署全部字节不变 | PASS — j1h2b-forgot-reset/ 之外 diff 为 0 |
| Harness 恰好 25 文件；detached worktree porcelain 0 | PASS |
| V2 STOP `3fb185be` 与 V3 STOP `888fd207` 未修改 | PASS — 两 report 分支 tip 仍精确指向原 SHA |

## Phase 2 — 协议真实性（12/12 PASS）

以 `R4-NEUTRALITY-PROTOCOL-CORRECTION.md` 为权威记录逐项核验：

1. 旧 raw-body byte equality 明确标记 **SUPERSEDED** — PASS（R4 文档 + CSV F3/F4/F5 注记 `[B1-R3]…旧逐字节对比已被 R4 纠正取代`）。
2. 唯一豁免是顶层 timestamp 的**值** — PASS（显式 sentinel 替换 `TIMESTAMP_SENTINEL='CANONICAL_TIMESTAMP_SENTINEL_B1_R3'`；存在性/类型/格式仍强制）。
3. 顶层 key 集精确 `{success,data,message,timestamp}` — PASS（`NEUTRAL_ENVELOPE_KEYS` 显式成员检查 + 数量相等检查，无删除/过滤路径）。
4. `success === true` — PASS（严格布尔判定）。
5. `data` 精确空对象 — PASS（非对象/null/数组/含键均拒）。
6. message 类型为 string、进入 canonical payload、钉住既有中性常量 — PASS（`pinnedMessageMatches` 对照产品真实常量；已核验 `backend/services/password_reset_service.py:63 NEUTRAL_PASSWORD_RESET_MESSAGE` 与 harness 钉住值逐字符一致）。
7. timestamp 存在、字符串、`Date.parse` 可解析 — PASS（三分类：missing/not_string/unparseable）。
8. 额外字段 fail closed — PASS（G3 五探针 accountExists/eligible/userId/tenant/request_id 全部拒绝且分类正确）。
9. 无通用 key 删除、filter、正则黑名单或递归忽略 — PASS（源码核验 + validator 对 core 模块禁 `delete `/`.filter(` 并强制契约面标记）。
10. canonical serialization 固定字段序 + timestamp sentinel — PASS（JSON.stringify 字面量固定四键序；G1 同时验证键序无关性）。
11. F3/F4/F5 status、canonical SHA、canonical length、可见文案一致 — PASS（spec 断言矩阵见 Phase 3）。
12. 不声称关闭统计型 timing side channel — PASS（R4 文档第 11 条明示 OUT OF SCOPE）。

## Phase 3 — 实现真实性（10/10 PASS）

1. `check-neutrality.mjs` 转译并执行**真实** `neutrality-core.ts`（readFileSync + ts.transpileModule + 动态 import 转译产物），零复制实现 — PASS。
2. `captureForgotFingerprint` 原始 body 仅存在于 route handler 局部作用域，canonicalize 后立即释放 — PASS。
3. 状态仅保留 `CanonicalFingerprint{status,message(公开常量字段),canonicalSha256,canonicalLengthBytes}`；无 raw body/timestamp 值/邮箱/完整信封 — PASS。
4. 错误输出仅固定 category/field 名 — PASS（`NeutralEnvelopeError` 构造即固定分类字符串；G6 泄漏探针验证 message+stack 无内容）。
5. F3/F4/F5 均执行 `pinnedMessageMatches` — PASS（spec 三处断言）。
6. F4 与 F5 均对 F3 执行 `sameCanonicalFingerprint`（sameFingerprint 别名）— PASS（F5 为 B1-R3 新增）。
7. F5 原有"无邮件/无 token"负向后置条件未削弱 — PASS（diff 显示 negativeWindowHasLink 15s 窗口断言原样保留，改动仅为新增断言）。
8. 24 browser + 5 non-browser = 29；节点名称与顺序不变 — PASS（新旧 CSV DictReader 逐行 (node_id, execution_class) 序列完全相等；--list 24 有序相等）。
9. serial、workers=1、retries=0、maxFailures=1 不变 — PASS（validator comment-stripped 强制）。
10. R12 application-settle 条件、RT0 BLOCKED_BY_H2_C、LF 合同不变 — PASS（validator 步骤 [4]/[5]、registry 在 delta 中零改动）。

## Phase 4 — Lubuntu 原生 Linux fresh checkout 门禁（全 PASS）

fresh detached checkout（porcelain 0）；Kilo Windows/autocrlf 侧由独立执行方交付：

| 门 | 结果 |
|---|---|
| `pnpm install --frozen-lockfile` | PASS（lockfile 零漂移，无新依赖） |
| `pnpm exec playwright test --list` | PASS — 24 tests / 1 spec，有序一致 |
| `node tools/check-neutrality.mjs` | PASS — Executable neutrality contract check PASSED (**G1–G6**) |
| `node tools/validate-static.mjs` | PASS — **STATIC GATE PASSED 7/7**（新增第 [7] 步执行可执行中性检查） |
| `pnpm exec tsc --noEmit` | PASS（exit 0） |
| `git diff --check cb352079..8c7e847` | PASS（clean） |
| scoped detect-secrets（tests/src/tools/config/inventory/docs/.gitattributes/.gitignore） | PASS — 0 findings |
| UTF-8/no-BOM/no-CR（独立字节复核，非复用 validator） | PASS — **25/25 LF-only**，BOM 0、CR 0、严格 UTF-0 违例 |

## Phase 5 — 独立变异 M1-M6（每项指定 RED → 还原 → GREEN）

| 突变 | 命中的指定 RED |
|---|---|
| M1 恢复 raw-body SHA 比较 | check-neutrality exit 1 — `G1: envelopes differing only in timestamp value (and key order) must be canonically equal` 失败 |
| M2 从 canonical payload 删除 message | check-neutrality exit 1 — `G2: a differing message must break canonical equality` 失败 |
| M3 放行任意 volatile key（删数量守卫） | check-neutrality exit 1 — G3 五个 added-key 探针全部"must be rejected"失败 |
| M4 跳过 timestamp 存在/类型/格式验证 | check-neutrality exit 1 — G4 三个 fixture（non-string/unparseable/empty）"must be rejected"失败 |
| M5 删除 F5 canonical equality | validate-static exit 1 — `F5 must assert canonical response equality against F3 (sameFingerprint(f3, f5))` |
| M6 将 raw body/timestamp 内容写入错误输出 | check-neutrality exit 1 — `G6: failure/error output must never contain envelope content`（LEAK_MARKER 命中） |

每次变异后字节还原（porcelain 归零）。最终复验：check-neutrality G1–G6 PASSED、validate-static **7/7**、--list 24 tests / 1 file、worktree HEAD == `8c7e847` 且 porcelain 0；**9 个候选文件 blob 逐一与 CANDIDATE 提交相等（零漂移）**。

## 附注与披露

- 本报告仅为 LUBUNTU 半边；不代 Kilo 声明任何 Windows/core.autocrlf=true 侧结果。
- inventory CSV 在 delta 中被修改，但仅限 F3/F4/F5 行的安全断言/期望/注记列文本更新（[B1-R3] 标注）；节点 id/class/顺序/计数经机器比对完全不变。
- 未声称执行过权威浏览器旅程；V2/V3 历史 STOP 保留原样未被重述为本轮证据。
- 下一步（CTO 批准后）：独立 fresh-runtime 单次权威浏览器执行。
