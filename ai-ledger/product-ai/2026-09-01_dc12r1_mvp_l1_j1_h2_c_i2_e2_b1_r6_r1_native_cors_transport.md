# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R1 — Native CORS Transport (Ambient Fetch Substitution Closure / AMBIENT_GLOBAL_FETCH_SUBSTITUTION__CORS_AUTHORITY_BYPASS)

- 日期：2026-09-01（+08:00）；执行者：Zcode
- BASE：`898fcaae1b9bfaffbb4887cce44eed438f2d2932`（B1-R6 候选；候选与远端
  引用未修改）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r1-native-cors-transport-2026-09-01`
- 验证层级：`V3_MERGE_CRITICAL`
- 声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`

## 0. SHA 身份层（当前控制面绑定模型，精确记录；后续引用遵守命名纪律）

| 层 | 绑定对象 | 证明方式 | 漂移类别 |
|---|---|---|---|
| L1 | profile committed blob @ canonical toplevel live HEAD | `git cat-file blob HEAD:<rel>` 与工作树字节比对（构造时 + 每检查点） | `profile_dirty_vs_head` / `profile_sha_drift` |
| L2 | contract：任务私有文件 live 字节 | authorize/launch 重读重算 | `contract_sha_drift` |
| L3 | materialized input：私有深冻结投影 canonical JSON | authorize/launch 重算 | `input_sha_drift` |
| L4 | candidate：canonical toplevel live `git rev-parse HEAD` | 构造/authorize/launch live 解析 | `candidate_sha_drift` |
| L5 | argv：精确 argv JSON | authorize 绑定、launch 复验 | `argv_drift` |

命名纪律：`0e711e32200ab4741c11cb51752d9adbfea4c455` 仅是 **B1-R5-R2 候选**；
`18d71fd1…`=R3 候选；`898fcaae…`=B1-R6 候选（本轮 BASE）；**当前 candidate
仅为本轮 tip**。历史提交不得互相混称。

## 1. Delta（恰为授权范围：4 文件 + 本台账 = 5 路径）

`tools/browser-authority-runner.mjs`（修改：原生 transport）、
`tools/check-browser-authority-contracts.mjs`（修改：+R27）、
`tools/validate-static.mjs`（修改：[14] 负检查 + 锚点）、`README.md`
（修改：R6-R1 小节）、本台账。产品/迁移/依赖/lockfile/harness-governance/
.secrets.baseline：零字节变化。

## 2. 修复 — AMBIENT_GLOBAL_FETCH_SUBSTITUTION__CORS_AUTHORITY_BYPASS

- `corsPreflightProbe` 不再引用 `globalThis.fetch`（或任何 ambient/限定
  fetch）：CORS OPTIONS 改经**模块私有** `node:http`/`node:https` transport
  （`nativeCorsOptionsRequest`），不接受调用方 transport。
- Origin、target、method（OPTIONS）、声明头（ACRM: POST / ACRH:
  content-type）、超时（`req.setTimeout` 10s → `CORS_PROBE_TIMEOUT`）与
  精确 Allow-Origin 判据全部保持不变。
- 响应被 drain 并归约为 `{status, allowOrigin}`；`Connection: close`；
  原生层不跟随重定向。

## 3. R27 — 环境替换真实性矩阵

注入的 ambient fetch 为**成功伪造**（回显正确 allow-origin——构成完全旁路
的最强形态）：

1. **PRE-import 替换（真实子进程）**：child 以
   `globalThis.fetch = <success fake>` 先于
   `import('./tools/browser-authority-runner.mjs')` 执行；绑定不可达目标
   （127.0.0.1:9）；probe 必须真实失败：
   `cors_probe_no_response`、STOPPED、**未进入 PREFLIGHTED/AUTHORIZED**、
   starts=0；child 输出
   `R27 AMBIENT_SUBSTITUTION_BLOCKED pre=cors_probe_no_response …`。
2. **POST-import 替换（进程内）**：替换 `globalThis.fetch` 后同上断言。
3. **正确真实服务器仍通过**：ambient fetch 被毒化（返回错误 allow-origin）
   时，可达的本地真实服务器流程照常 FINISHED——probe 走原生 transport，
   ambient 不被咨询。
4. **错误 Origin / HTTP RED / timeout 仍 fail-closed**：三者共用同一原生
   transport（R26 矩阵模式不因 ambient 替换改变；wrong/400/timeout 模式
   分类保持）。

## 4. 文件级变异 — BYPASS_ACCEPTED 复现

将 transport 退化为 `await fetch(...)`（ambient）后：

- child stdout 字节证据：`BYPASS_ACCEPTED pre-import state=STOPPED`
  （exit 2）——不可达目标被 ambient 伪造响应"回答"，替换即被标记；
- checker **RED rc=1**（child 非零退出 + R27-POST 断言）；
- runner 按快照字节一致恢复 → checker GREEN rc=0；
- **tree integrity before == after**（6 文件 manifest SHA-256）。

过程披露：mutation 下 child 的 BYPASS 表现形态为 ambient 伪造响应被
allow-origin 判据拒绝（fake 未回显正确 origin），故观测到的分类为
`cors_allow_origin_mismatch`——但响应本身来自 ambient 伪造（不可达目标
不可能产生真实响应），替换事实成立，`BYPASS_ACCEPTED` 按 CTO 命名打印。

## 5. 冻结门

fetch 后 BASE local==remote（R6 tip 比对）；impact `corsPreflightProbe`
**MEDIUM(6)**（BASE 索引；非 HIGH/CRITICAL，继续并披露——6 个受影响调用者
均为本轮改造的 CORS 流自身）；frozen-lockfile PASS；`test:list` 15/1 顺序
不变；`validate:static` **14/14**（[14] 新增：`node:https` 导入、
`nativeCorsOptionsRequest`、R27 标记、**runner 内禁止任何 `fetch(` 调用
形态**的负检查）；G1–G6；runtime-contracts；browser-authority
（R1–R27）；tsc；`git diff --check` clean；detect-secrets 只读 rc=0；4 文件
UTF-8/LF 清洁；detect_changes staged 实测数字见提交信息。

## 6. 禁止项遵守

无 PG、无 Redis、无产品运行时、无非 list Playwright、无权威浏览器旅程、
无 Kilo/合并/部署；B1-R6（`898fcaae`）及更早历史未修改、未重写、未
force-push。

## 7. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_R1_CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY**

声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_DELTA_REVIEW_ONLY`。推送后
STOP，等待 Kilo。

**STOP。**
