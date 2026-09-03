# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R2 — Process-Isolated CORS Probe (MUTABLE_NODE_BUILTIN_TRANSPORT__CORS_AUTHORITY_BYPASS Closure)

- 日期：2026-09-01（+08:00）；执行者：Zcode
- BASE：`d6a0258bc88272d92b427c82b7d198f551482540`（B1-R6-R1 候选；候选与远端
  引用未修改）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r2-process-isolated-probe-2026-09-01`
- 验证层级：`V3_MERGE_CRITICAL`
- 声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`
- 输入：CTO 裁决 `STOP_AND_RETURN_FOR_B1_R6_R2`（P1：candidate 将注入点从
  globalThis.fetch 转移到可变的 node:http 默认导出对象——launcher 在导入
  runner 前替换 `http.request` 即 BYPASS_ACCEPTED + state=AUTHORIZED +
  real_network_calls=0；只读反例已在其原字节上证实）

## 1. 信任边界（本.Handler 轮的结构性修复）

1. **同进程 transport 宣言撤回**：B1-R6-R1 的"module-private transport 不可
   替换"不成立——`node:http` 默认导出对象共享且可变。runner 内的
   `node:http`/`node:https` 导入与 `nativeCorsOptionsRequest` **整体删除**；
   控制面主进程不再做任何网络 I/O。
2. **进程隔离 probe**：权威 CORS probe 由全新独立 node 子进程执行
   （`process.execPath` 固定、argv 数组 `[helperPath]`、环境剥除全部
   `NODE_*`/`GIT_*` —— NODE_OPTIONS/NODE_PATH/preload 注入与 GIT_* 劫持
   均不可能）。探针输入经**私有 stdin** JSON 传递（origin/target/
   timeoutMs）；URL/凭据不进 argv、日志或证据。
3. **helper 规范路径 + committed blob 绑定**：helper 为规范同目录文件
   `tools/browser-authority-cors-probe-helper.mjs`；每次 probe 前证明其
   工作树字节 == 所属仓库 live HEAD 的 committed blob
   （`git cat-file blob HEAD:<rel>`），不等即
   `cors_helper_dirty_vs_head`（STOPPED、starts 不动）。
4. **authority evidence 铸造权**：仅进程隔离 probe 通过才置
   `#corsProbePassed`；直接 import ControlPlane 的同进程路径不产生任何
   authority evidence（probe 结果只来自 pristine child 的分类 JSON）。
5. **判据不变**：OPTIONS 到派生 target、Origin=派生 base_url Origin、
   ACRM: POST / ACRH: content-type、10s deadline、2xx + Allow-Origin 精确
   相等。

## 2. Delta（恰为授权范围 + helper：6 路径）

| 文件 | 类型 |
|---|---|
| `tools/browser-authority-cors-probe-helper.mjs` | 新增（pristine 进程 probe helper） |
| `tools/browser-authority-runner.mjs` | 修改（child spawn probe；删除进程内网络导入） |
| `tools/check-browser-authority-contracts.mjs` | 修改（+R28 矩阵） |
| `tools/validate-static.mjs` | 修改（[14] 锚点重构） |
| `README.md` | 修改（R6-R2 小节） |
| 本台账 | 新增 |

产品/spec/迁移/依赖/lockfile/harness-governance/profile/schema/
.secrets.baseline：零字节变化。

## 3. R28 — 同进程替换矩阵（毒化 launcher 进程后全部 fail-closed）

毒化形态：`globalThis.fetch` 成功伪造（回显 allow-origin）+
`http.request`/`https.request` 成功伪造（回显 Origin、计数 fakeCalls、
零真实网络）+ `syncBuiltinESMExports()` 固化——对不可达目标
（127.0.0.1:9）：

- probe → `cors_probe_no_response`（pristine child 真实连接失败）；
- state=STOPPED，**未进入 PREFLIGHTED/AUTHORIZED**，starts=0，
  fakeCalls=0（runner 从不咨询 launcher 进程的伪造绑定）；
- 正控：可达真实服务器在同样毒化下 probe 通过 + 全流程 FINISHED
  （进程隔离证明）；
- wrong-origin / 400 / timeout 探针在毒化下保持原 fail-closed 类别
  （R26 模式经同一 child 通道）；
- BYPASS 检测器：若 probe 在不可达目标上被接受，则驱动
  preflight+authorize 并记录
  `R28 BYPASS_ACCEPTED state=<state> real_network_calls=<server delta>`
  ——该消息仅在退化 runner 下出现（见证伪）。

## 4. 文件级变异 — BYPASS_ACCEPTED + AUTHORIZED + real_network_calls=0

M-R6R2：将 child-spawn probe 退化为进程内 `http.request`（re-import
node:http + 原地调用）后，R28 毒化场景输出精确三元组
`R28 BYPASS_ACCEPTED state=AUTHORIZED real_network_calls=0`
（fake 被调用但零真实网络），checker RED rc=1；按快照字节一致恢复 →
GREEN rc=0；tree integrity manifest before==after。state=STOPPED 不计作
bypass 复现。

## 5. 冻结门

fetch 后 BASE local==remote（R6-R1 tip 比对）；impact `corsPreflightProbe`
MEDIUM(6)（BASE 索引，非 HIGH/CRITICAL，继续并披露）；frozen-lockfile
PASS；`test:list` 15/1 顺序不变；`validate:static` **14/14**（[14] 重构：
runner **禁止** `node:http/node:https` 导入与进程内 `.request(` 调用
（网络 I/O 只在 helper child），helper 原生 transport + 精确判据锚点，
R28 标记）；G1–G6；runtime-contracts；browser-authority（R1–R27 + R28）；
tsc；`git diff --check` clean；detect-secrets 只读 rc=0；6 文件 UTF-8/LF
清洁；detect_changes staged harness 内部（数字见提交信息）。

**门序披露**：helper 的 committed-blob 绑定要求其已在 HEAD 中提交，故本轮
门禁在 candidate commit 之后、push 之前于提交态执行（干净工作树，工作树
字节 == HEAD blob）。

## 6. 禁止项遵守

无 PG、无 Redis、无产品运行时、无非 list Playwright、无权威浏览器旅程、
无 Kilo/合并/部署；B1-R6-R1（`d6a0258b`）及更早历史未修改、未重写、未
force-push；SKU 双线未合并、未占用 H2-C 资源。

## 7. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R2_CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY**

声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`。线性推送
后 STOP，等待 Kilo bounded delta review。

**STOP。**
