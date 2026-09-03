# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6 — Mandatory Runner-Owned CORS Preflight Probe

- 日期：2026-08-31（+08:00）；执行者：Zcode
- BASE：`ba9153ecdbfa38f8cfd0eccb8bce8e70656f0c3a`（B1-R5-R4-R1 候选；候选与
  远端引用未修改）
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-cors-preflight-probe-2026-08-31`
- 验证层级：`V2_BROWSER_AUTHORITY_PREFLIGHT_CONTRACT`
- 声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`

## 1. Delta（恰为授权范围：4 文件 + 本台账 = 5 路径）

runner（修改，+runner 自有 CORS probe）、checker（修改，+R26 矩阵 + 本地
CORS fixture server）、validate-static（修改，[14] 锚点扩展）、README
（修改，R6 小节）、本台账。profile/schema 未需改动。产品 backend/frontend、
spec、迁移、依赖、lockfile、harness-governance：零字节变化。

## 2. 十项关闭落点

1. **probe 为 runner 自有强制步骤**：`corsPreflightProbe()` 由 runner 构造
   请求（Origin/target/头/判据全部在 runner 内），`preflight()` 无
   `#corsProbePassed` 即 `cors_probe_missing`——launcher 的任意 ok=true
   布尔值在结构上不可能替代。
2. **Origin/target 派生**：Origin 仅从已绑定 base_url 解析
   （`deriveBrowserOrigin`），目标仅从已绑定 api_base_url 解析
   （`deriveCorsTarget`）——均为私有深冻结 input 的值，调用方不可指定。
3. **无副作用 OPTIONS**：对 `/client/auth/forgot-password` 发
   `OPTIONS`，声明 `Access-Control-Request-Method: POST` +
   `Access-Control-Request-Headers: content-type`；`redirect: 'error'`、
   `AbortSignal.timeout(10s)`。
4. **通过判据**：响应 2xx 且 `Access-Control-Allow-Origin` 精确等于派生
   Origin。
5. **authorize 前 STOP**：4xx/5xx → `cors_probe_http_error`；无响应 →
   `cors_probe_no_response`；超时 → `cors_probe_timeout`；allow-origin 缺失
   或不匹配 → `cors_allow_origin_mismatch`；一律 STOPPED、launchStarts=0。
6. **不可绕过**：省略 probe → preflight 即 `cors_probe_missing`；伪造
   caller check（任意标签/类别的 ok=true 数组）同拒；重复 probe →
   `cors_probe_already_invoked`（先落账再 STOPPED）。
7. **证据卫生**：CORS 台账项仅含 kind/ok/status_2xx/allow_origin_present/
   allow_origin_exact 布尔；checker 断言 sink 无 `http://127.0.0.1` 与路径
   字符串；值防火墙照常生效。
8. **真实性矩阵 + mutation**：见 §3/§4。
9. **R1–R25 全部保持 GREEN**；`test:list` 仍 15 tests / 1 spec 顺序不变。
10. 产品源码/backend/frontend/迁移/依赖/lockfile 零变化。

## 3. R26 真实性矩阵（本地 http fixture server，六模式）

| 场景 | 结果 |
|---|---|
| POS：ok 模式全流程 | OPTIONS 方法/路径/ACRM/ACRH/Origin 逐项精确断言；probe+preflight+authorize starts=0；repeat → `cors_probe_already_invoked` |
| OMIT | preflight → `cors_probe_missing`，STOPPED，starts=0 |
| FAKE | caller ok=true 数组（含 caller_cors_ok 标签）→ `cors_probe_missing` |
| wrong allow-origin | `cors_allow_origin_mismatch`，STOPPED，starts=0 |
| missing allow-origin | `cors_allow_origin_mismatch`（present=false 入账） |
| 400 / 500 | `cors_probe_http_error` |
| timeout（hold 连接） | `cors_probe_timeout`（AbortSignal.timeout(10s)） |
| 证据卫生 | durable sink 无 URL/路径字符串 |

每例后全新实例规范 GREEN 路径复验；mode 在循环内先复位再 greenPath。

## 4. 文件级变异（tree integrity before == after
`1dab59aa…4f8708`）

删除 preflight 的强制 CORS enforcement（`if (false && …)`）→ checker rc=1，
精确消息 `R26-OMIT: preflight without the runner-owned probe did NOT throw`；
runner 按快照 SHA `b0ec7cce…` 字节一致恢复 → checker GREEN rc=0。

## 5. 冻结门

fetch 后 BASE local==remote（R4-R1 tip 比对）；impact `preflight` LOW(2)/
`materializeInput` LOW(1)（BASE 索引，无 HIGH/CRITICAL）；frozen-lockfile
PASS；list 15/1 顺序不变；static **14/14**（[14] 锚点扩展
CORS_PREFLIGHT_PATH/cors_probe_missing/cors_allow_origin_mismatch/
AbortSignal.timeout/ACRM+ACRH 声明/R26）；G1–G6；runtime-contracts；
browser-authority（R1–R25 + R26 矩阵）；tsc；diff-check clean；
detect-secrets 只读 rc=0；改动文件 UTF-8/LF 清洁；detect_changes staged
harness 内部（数字以实测入提交信息）。

## 6. 禁止项遵守 + 边界

无 PG、无 Redis、无产品运行时、无非 list Playwright、无权威浏览器旅程、
无 Kilo/合并/部署。R1–R4-R1 历史（含 `ba9153ec`）未动。CORS probe 在测试
中指向本地 fixture server；真实环境的探测将在 Kilo 后的单栈单 preflight
单浏览器门中随真实绑定 URL 执行。probe 走真实网络栈（global fetch），不存
在可被 launcher 掉包的实现注入点。

## 7. 裁决

**PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R6_CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW**

声明上限：`CANDIDATE_READY_FOR_KILO_BOUNDED_REVIEW_ONLY`。推送后 STOP。
B1-R6 完成后必须经过 Kilo bounded review；随后 Lubuntu 使用任务独占 PG、
Redis、网络、卷和端口执行新的单栈、单 preflight、单浏览器门。

**STOP。**
