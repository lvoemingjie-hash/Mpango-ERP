# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R5 — Browser Authority Control-Plane Source Closure

- 日期：2026-08-31（+08:00）；执行者：Zcode
- BASE：`cbe5362663128f6b7e6ed551f68b1818e468953b`（B1-R4 候选）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r5-browser-authority-control-plane-closure-2026-08-31`
- 验证层级：`V3_MERGE_CRITICAL`
- 声明上限：`SOURCE_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`

## 1. 目标与背景

R2 独立轮（`ef33a882`）暴露的 launcher 缺陷（runner E2BIG 未启动即 VOID、
外部门账/输入/SHA 纪律缺失）在本轮被改造为**仓库内、可审查、可证伪的执行
控制面**：未来任何被授权的浏览器权威 launcher 必须由该控制面驱动。

## 2. Delta（相对 BASE，恰为授权范围）

| 文件 | 类型 |
|---|---|
| `j1h2c-retailer-recovery/tools/browser-authority-runner.mjs` | 新增（控制面状态机） |
| `j1h2c-retailer-recovery/tools/check-browser-authority-contracts.mjs` | 新增（真模块契约检查器） |
| `j1h2c-retailer-recovery/inventory/browser-authority-contract.schema.json` | 新增（契约 schema，仅标签与 env 变量名，永无值） |
| `j1h2c-retailer-recovery/tools/validate-static.mjs` | 修改（+步骤 [13]，12/12→13/13，如实披露） |
| `j1h2c-retailer-recovery/package.json` | 修改（+`check:browser-authority` 脚本） |
| `j1h2c-retailer-recovery/README.md` | 修改（+控制面章节，"implemented, NOT run"） |
| 本台账 | 新增 |

产品 backend/frontend、`tests/recovery.spec.ts`、inventory node registry、
Playwright config、pnpm-lock.yaml、harness-governance、candidate 历史：
零字节变化。

## 3. 十项关闭的落点

1. **禁止 destructive merge 覆盖 `owner_email_label`**：`mergeMaterialized`
   对 owner label 键与 owner field 绑定一律
   `owner_label_overwrite_forbidden`。
2. **materialized input 逐字段投影 + W1/W2 严格必需**：仅接受契约声明字段；
   任一 required 字段缺失/空 → `required_field_missing`（仅报字段标签）；
   投影结果以 `inputSha`（SHA-256 over 精确 JSON）绑定。
3. **transition `from` 先捕获**：`transition()` 在任何状态变更前捕获
   current，不匹配即 `transition_from_mismatch` 且状态保持不变；边必须
   在契约 transitions 内。
4. **terminal STOP 后拒绝全部入账**：STOP 后每个控制面调用先写
   `rejection_after_stop` 台账项再抛 `terminal_stop`；
   `verifyRejectionsLedgered` 不变量使"拒绝未入账"可检出
   （`rejection_unledgered`）。
5. **preflight 恰一次**：`preflight_already_invoked`；checks 数组内任一
   RED 或任何异常立即 `stop()` VOID。
6. **VOID 后冻结**：`guardLive` 使 preflight/authorize/launch 在 STOPPED
   后全部 `terminal_stop`；输入/契约对象不改写、无重跑、无换栈、无浏览器。
7. **browser authority 最多启动一次**：`launchStarts` 哨兵先于任何 I/O；
   重复 → `launch_already_invoked` + 台账。
8. **四重 SHA 绑定**：authorize 绑定 contractSha/inputSha/candidateSha/
   argvSha；launch 启动前全部重新校验（漂移即 VOID：
   `contract_sha_drift`/`input_sha_drift`/`candidate_sha_drift`/`argv_drift`）。
9. **证据只含名称/布尔/类别/计数**：`evidence()` 输出白名单字段；
   `AppendOnlyLedger.append` 对条目做敏感值防火墙
   （`sensitive_value_rejected`）；fixture 值永不进入输出。
10. **子进程 argv 数组、零 shell**：launch 通过注入的 execFile 式实现调用
    `argv[0], argv.slice(1)`；非数组/空数组/非字符串项 → `argv_not_array`；
    runner 中无 `spawn(`、无 `shell:true`（validate-static 步骤 [13] 常驻
    检查）。

## 4. 真实性门

- **真模块加载**：检查器以 `await import('./browser-authority-runner.mjs')`
  加载真实模块（无平行实现复制）；S0 用真实 schema 文件校验 fixture 契约。
- **规范 GREEN 路径**：materialize → preflight（全 OK）→ authorize →
  经注入 double 的单次 launch；evidence 断言无 fixture 值；同 env 的两次
  materialize 产生**相同 inputSha**（确定性投影绑定）。
- **≥10 个 RED 反例**（每例必须抛出**精确类别**，错类别或不抛即检查器
  FAIL）：R1 字段覆盖（owner label 键 + owner field 绑定两探针）、
  R2 缺 owner label/缺 W1/缺 W2、R3 错误 from（含非法边）、
  R4 拒绝未入账（剥离台账触发 `rejection_unledgered`，真实台账通过
  不变量）、R5 VOID 后 preflight/authorize/launch 三面 + 三条
  rejection_after_stop 入账、R6 第二次 preflight、R7 第二次 browser
  （double 恰执行一次）、R8 candidate/input/contract SHA 漂移三探针 +
  漂移面终态验证、R9 argv 漂移 + 字符串 argv（authorize/launch 两面）+
  空 argv、R10 敏感值入账（email/password 值 + 文本嵌 W1 码）+ 纯类别
  note 接受为对照。每例之后以全新 ControlPlane 复跑规范路径并要求 SHA
  绑定一致（恢复→re-GREEN）。
- **文件级证伪 ×2**（对最终候选 runner，快照 SHA-256
  `12df1e072c06364facb8dc511c907c37a2d495ae13b44ad6b1e64040f6b19586`）：
  M1 关闭 owner-label 守卫 → 检查器 RED rc=1（R1 抛出
  `undeclared_field` 而非要求的 `owner_label_overwrite_forbidden`）；
  M2 关闭 launch 哨兵 → 检查器 RED rc=1（R7 抛出
  `transition_from_mismatch` 而非 `launch_already_invoked`）。
  两次均按快照**字节一致恢复**（SHA-256 相等验证）并重新 GREEN rc=0。
  错误类别/未命中/其他错误一律不计为 RED。

## 5. 冻结门（全部在本轮 worktree 执行）

- `pnpm install --frozen-lockfile`：PASS。
- `pnpm run test:list`：**15 tests / 1 spec**，顺序不变（validate-static
  步骤 [3] ordered-equal 同步验证）。
- `pnpm run validate:static`：**13/13 PASS**（步骤计数 12→12→13，新增
  [13]，如实披露）。
- `pnpm run check:neutrality`（G1–G6）：PASS。
- `pnpm run check:runtime-contracts`（含 B1-R4 loader）：PASS。
- `pnpm run check:browser-authority`（本轮新增）：PASS。
- `pnpm run typecheck`：PASS。
- `git diff --check`（BASE→staged）：clean rc=0。
- 只读 detect-secrets（六个改动文件 vs `.secrets.baseline`）：rc=0；
  checker 内两行合成 fixture（password 标签 + 明显假值）按 HE2 轮先例
  以 `// pragma: allowlist secret` 标注。
- 改动文件严格 UTF-8 / 无 BOM / 无 NUL / 无 CR / LF-only：PASS
  （修复过程中一次 Python 转义事故产生的 0x08 退格字节已被字节级清除，
  终态文件 0 控制字节）。
- 编辑前 GitNexus impact（索引 commit == BASE `cbe5362`）：
  validate-static 的 `ok`/`fail`/`walk` 上游 impact 均 **risk LOW**。
- 提交前 GitNexus detect_changes（staged）：见 §7。

## 6. 本轮禁止项遵守声明

无 PG、无 Redis、无产品启动、无非 list Playwright、无浏览器权威运行、
无 launcher 实际环境重跑、无合并或部署。控制面 launch 仅在测试 double
上证明纪律，从未触及真实进程。

## 7. GitNexus detect_changes（提交前）

`detect_changes(scope=staged)`（index 于 BASE `cbe5362`）：
预期仅 harness 内部、无产品流程漂移（结果数字见提交信息与 review 记录）。

## 8. 证据真相

- 本轮是**源码闭环**：控制面已实现并被机器门证明，但从未驱动真实浏览器。
- `ef33a882`（Lubuntu V2）的后端 zero-red 归属该轮，不因本轮改变；其
  浏览器 NOT_RUN 阻断（B1-R4 已修的 loader 缺陷）的最终解除仍需未来
  被授权轮**经由本控制面**完成。
- 无浏览器 PASS、无 launcher 环境 PASS、无合并或部署声明。

## 9. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R5_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW**

声明上限：`SOURCE_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`。
推送后 STOP。下一门仅为 Kilo bounded source/test authenticity review；
不自行启动 Lubuntu、浏览器权威运行、合并或部署。

**STOP。**
