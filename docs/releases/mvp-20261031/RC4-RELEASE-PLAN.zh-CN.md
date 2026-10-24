# RC4 当前候选本地准入与发布待决计划

授权 CTO-AUTH-MVP-RC4-CURRENT-CI-INTAKE-CODEXL-R1-20261024。本文是实现者方案，非 CTO 源码接受、独立验收、全量或发布 PASS。

## 来源与保护

产品 BASE 为 bb625e893ab1ec3c50c7eb0cfeedf4a73e9f8f6b，唯一父为 3ec7f94db3b46a18d4805a4a00a6c0d7fa26790e。七条当前迁移头测试合同先以普通提交 cffc1271a8746cb5d8fe8dc6690f4880a6da0b1d 冻结；CI/coverage 在其普通 successor 中接续该已存在 source，不引用未来自身 SHA。source-continuation 为 AUTHOR_PROPOSAL_PENDING_CTO，不宣称已经获 CTO 对新候选的来源/语义接受。

frontend 树固定 17c477ca022b0dc86118f481fd4ded907e92bcf8，产品 API/services/models、043/044 和全部其他迁移、依赖锁保持 BASE mode/blob。backend 仅计划中七条已有测试路径允许当前头合同的精确同步；历史升级起点/终点、原 nodeid、安全和经济预言保持。治理记忆/运营文档由 B 线负责，本候选不改。

## 当前测试宇宙

Git 跟踪 test_*.py 共277文件；六个固定 ignore 不动；271非ignore文件精确分为250普通、21历史专用文件，交集与未知成员均0。新 staff/库存/audit 文件不能因失败被排除。普通分区仍为 runtime-a/runtime-b/topology/invariants-jwt/task-managed-pg 五腿，真实 JWT 及其 fixture/env 消费面由机器分区和 RC4-TEST-SELECTION.json 明列。

staff/inventory HTTP 需要 staging/JwtAuthStrategy、dev_sink、044 schema 和任务所有权证明；audit 新原生 full_world 需要同一 mpango_app 的 AUDIT_FINITE_APP_URL、私有 AUDIT_FINITE_PRIVATE/facts 与独立 EXPORT_DIR。它们接入普通 JWT 腿，不提升 app 权限、不更改断言或 auth 实现。migration/operator/reporting 保留既有角色隔离。未显式供给的外置胶囊或服务不能伪装已运行，未来未知专用成员仍拒绝。

原始 collect 各腿仅一次，verbosity=-1、当前 pytest.ini/严格 markers 不变。节点原文不改写，重复拒绝。canonical 配方：后端相对 nodeid 原样保留，按 Python 字符串顺序排序、UTF-8/LF、一个末尾 LF，SHA-256。当前节点计数和摘要仅由本轮原生 collect 及独立重算冻结；具体结果在 RC4-TEST-SELECTION.json，不沿用4288硬数。单次 smoke 至多8节点、五组串行，仅证明供给消费接通，不代替完整五腿 body。

## 历史复用与真实缺口

| 记录 | 可保留范围 | 当前不得外推 |
| --- | --- | --- |
| 1f3fd087 旧 hosted | 历史4227 passed +61 skip/xfail，原候选/原集合，不重写为本候选运行 | 不是当前277文件或新分区 body 通过 |
| M1/M2 旧观察 | 原 staff/库存有限观测与其 CTO 裁定，执行身份、准备与失败沿用原披露 | 不是当前整个 CI 或独立全量；不把分轮绿拼接成一次全量 |
| B-R01 | 按本次 CTO 正文登记124/15有执行偏差的有限回归；旧原件与偏差保留，本轮不重跑、不升级身份 | 不是全 audit 文件、全缓存或 release-critical-journeys 覆盖 |
| M01 R4 | CTO-FINAL-RULING 关闭 bb625e89 上单实例UG、合法缓存重放后撤权、403/BINDING_NOT_ACTIVE、原始经济多重集不变的具名链 | 不覆盖跨进程共享缓存、Redis缓存实现、首事务失败交错、全部sibling、浏览器/双国、SMTP、全量 |
| S1/S2/S3/照片 | 原 VERIFICATION-COVERAGE 的候选、原件、节点映射及接受范围完整保留 | 产品/支持/前端依赖已变处保留新依赖差异，不声称旧整树等于当前source |

M01 R4 原件为 AI_REPORT_INBOX/m01-r4-cto-final-acceptance-20261024/CTO-FINAL-RULING.zh-CN.md；本轮不补跑。旧节点映射与历史 bindings 不回写；current_dependency_assessments 对当前依赖重验保留 GAP。真实邮箱HTTP/SMTP注册、完整收入确认、未执行节点、迁移专用场景、当前浏览器及目标环境恢复仍按实际证据保留，不由本地工具合同或 M01 自动补齐。

## 下一次 test-only CI 预算提案

零次本轮远端写。拟维持五腿 job-timeout 为30/30/50/25/25分钟，总上限160 runner-minutes，max-parallel=2、fail-fast=false。body 外层18m/18m/38m/13m/13m，不吞失败，准备、精确收集、JUnit、脱敏和清理预算含于 job 上限。新 JWT 族时长只有 smoke 支撑，整腿耗时仍 UNKNOWN；此次数字是受限预算提案，不是可保证完成性 SLA。不得靠删除节点、跳过或改断言适配超时；超额/新阻断由 CTO 统一裁定。

测试始终执行；publish 默认 false，普通 push 和默认 dispatch 不进入 build/publish/deploy，任何测试失败均不能发布。消毒、精确 JUnit、五腿独立资源及并发约束不因来源接续削弱。test-only 远端动作必须另获 CTO 明示授权；本轮不 push/PR/dispatch/rerun/merge/deploy。

## 交回口径

最终以 task delivery 的原生 contract/collect/smoke/Vitest/build 回执、来源保护、调用/资源/秘密核销和未解决表为准。只有文件字节等价时才复用对应结果；文档后继不伪造新执行。正常 hook 的 baseline 机械元数据须逐字段证明1115条既有 finding 身份、审计、插件、过滤配置不变；任何新发现不得自行豁免。不能正常提交时交候选树与精确 hook GAP，不声称已提交。
