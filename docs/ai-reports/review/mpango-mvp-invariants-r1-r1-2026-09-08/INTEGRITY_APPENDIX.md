# 证据完整性附录（R1-R2 整改，2026-09-08）

> 针对 CTO 裁决 NEED_CHANGES_TEST_SAFETY_AND_EVIDENCE_INTEGRITY 的整改记录。
> 本轮授权范围：修正证据与措辞、补 Redis 归属和精确键清理测试、补齐全量逐节点对账；
> 不扩大产品修复、不重跑旧 VOID 任务、不合并不部署。

## 1. 冻结运行状态更正：POST_VOID_CONTINUATION

R1-R1 轮的候选冻结全量运行**不是**原授权意义上的首次正式验收运行：首次冻结运行因任务库未迁移
判为环境 VOID（`_zcode_mvp_invariants_r1r1_frozen_cand_VOID1.log`，材料归档未覆盖），随后加入
准备步骤并重执行。该续跑应标注为 **POST_VOID_CONTINUATION**：其证据效力为"该字节组合下的一次
完整运行记录"，不追溯为原授权下的正式验收；正式验收由独立 V3 在最终候选上执行。BASE 侧冻结
运行不受 VOID 影响（其容器/准备步骤独立且一次完成）。

## 2. 全量逐节点对账更正：完整解析 3837 / 3824

原 NODE_RECONCILIATION 的解析器要求状态词与百分比列之间恰一个空格，漏配 pytest 对短路径行的
多空格对齐（以及含空格参数化 id），只解析出 3590/3577。修正后的解析器（状态词取行内最后一个
token、允许多空格）完整恢复：

| 侧 | 逐节点结果行 | 与收集清单差 |
|---|---|---|
| 候选 | **3837**（=收集数 3837） | 40 个为 collect/verbose 参数转义渲染差（如 `C://Windows//...` vs `C:\\Windows\\...`），参数盲匹配 0 失配 |
| BASE | **3824**（=收集数） | 同上 |

完整差分（取代原 15/2）：

- **candidate-only = 18**（guards 7：exact_cto、chained 更名、5 反例；revocation 6：3 个 F1/F3
  新节点 + 2 个 F3 节点 + 诊断节点，全量内 ERROR=既有泄漏机制；concurrency 1：行数保留对照；
  u4d_intake_parser_preview 3：参数化 id 含空格；u6i3 1：随机 UUID 参数化实例）——除 6 个
  revocation ERROR 外全部 PASSED
- **base-only = 5**（guards 1：`rejects_duplicate_collapsed_to_two`（候选更名）；u4d 3；u6i3 1）
  ——全部 PASSED
- 共享节点状态变化：仍恰 1 处（丢失更新 RED→PASSED）
- FAILED 差：仅 BASE 1（同上）；ERROR 差：仅候选 6（同机制）；SKIP 集合 69/69 恒等；XFAIL 15/15

## 3. 秘密扫描更正：真实 detect-secrets-hook（argv/rc/结果）

此前的 `python -m detect_secrets.main hook …` 不是有效扫描入口（静默退出 0，无扫描动作），
**不作为证据**。本轮改用真实 hook 并以反例证明其非空操作：

- 工具：`_zcode_mvp_invariants_r0_venv/Scripts/detect-secrets-hook.exe`（v1.5.0）
- 反例证明：向临时文件植入一个 AWS Access Key 文档形状样例（AKIA 开头、公开文档示例值，字面量不在此复现以免触发扫描器）后
  argv=`detect-secrets-hook --baseline .secrets.baseline <临时文件>` → 输出
  "Potential secrets about to be committed to git repo! Secret Type: AWS Access Key"，
  **rc=1**（证明 hook 真实扫描）；临时文件已删除
- 正式扫描：argv=`detect-secrets-hook --baseline .secrets.baseline <候选累计全部 18 个变更路径>`，
  **rc=0**（基线之外零发现）；`.secrets.baseline` sha256
  `f49c86223abc95af12d0f6c60938050a68a84e332a94a444800cd93450bd16bf` 前后不变

## 4. 变更路径更正：18 个（非 12）

候选累计 diff（BASE a516d2b3 → 工作树）实际为 **18 个路径**（`git diff --name-only a516d2b3` 计数，
上表同源）：此前把上一轮的"12 文件"口径误沿用到本轮（该口径未计入 evidence/ 目录 6 个文件）。
本轮整改后累计路径以提交时的 `git diff --name-only` 为准，秘密扫描覆盖全部 18 路径（见 §3）。

## 5. 双哈希与 EOL 转换事实

仓库 checkout 为 CRLF（autocrlf），提交 blob 为 LF；运行以工作树字节执行。四份冻结测试文件：

| 文件 | 冻结运行字节 sha256（工作树，RUN_IDENTITY 所记） | 提交 blob sha256（LF，baea9943） | blob 内容+CRLF sha256 |
|---|---|---|---|
| test_mpango_mvp_invariants_r0_revocation.py | `a472cccb95f155e1…` | `ba9e123c4dd8742c…` | `a472cccb95f155e1…`（=运行字节，数值验证一致） |
| test_mpango_mvp_invariants_r0_concurrency.py | `7e9d1c25933b7f02…` | `fdd47eec8e3cc5fb…` | `7e9d1c25933b7f02…`（=运行字节，数值验证一致） |
| mpango_invariants_r0_support.py | `817f56f5de390623…` | `c757c1f0f8e7e521…` | `817f56f5de390623…`（=运行字节，数值验证一致） |
| test_mpango_invariants_r0_r1_guards.py | `f94b32d0858c04ad…` | `55e5f60b4451609b…` | `7627bfd619a18acc…`（≠运行字节，见下） |

EOL 事实：guards 文件在冻结时为**混合行尾**（主体 CRLF + 追加节 LF），故"blob 统一补 CRLF"不等于
其原字节。内容等价性由 git clean filter 的定义保证：提交时仅做 CRLF→LF 的行级规范化、不改任何
行内容字符，即 blob 内容 == 运行内容逐行去掉行尾差异；其余三文件给出数值验证（blob+CRLF 与冻结
哈希全等）。本轮整改后的新提交同样存在 CRLF(工作树)→LF(blob) 转换，运行字节以提交时工作树
sha256 记录（见 RUN_LOG §九）。

## 6. Redis 归属证明与精确键清理（新增，替代通配 SCAN）

- 新增 `verify_task_redis_ownership_sync`（support 模块）：删除动作前证明 Redis 任务归属——
  必须声明 `MPANGO_INVARIANTS_R0_REDIS_CONTAINER` + 任务命名空间 owner 标签 + REDIS_URL，
  `docker inspect` 核对标签/`redis:*` 镜像/6379→127.0.0.1:<URL 端口> 映射；任一不满足即
  `GUARD_REFUSED_REDIS_OWNERSHIP`，先于任何删除。
- `_delete_sku_list_cache_keys(keys)`：三态返回——`cache-unreachable`（不删也不需删，fail-open）、
  `refused-ownership`（可达但归属未证明：零删除，调用方不得建立前提）、`deleted=k`（精确删除
  所列键；**无 SCAN、无通配**）。对照节点的隔离前提与两个节点的 teardown 均只删除**自己计算出的
  精确键**（`skus_list:1:10:None:<本次唯一 q>`）。
- guards 新增 4 个单测：归属缺配置/异标签/非 loopback 三个拒绝负控（均在 docker 与删除之前拒绝）+
  精确键形状断言；35/35 PASS。
- 三前提实测（R=_zcode_mvp_invariants_r1r2_*.log，开发容器）：可达+已声明 → 对照 PASS
  （premise=deleted=1，主动证明）+ 诊断命名 RED；可达+未声明 → 对照 SKIP（fail-closed，
  `refused-ownership(GUARD_REFUSED_REDIS_OWNERSHIP…)`，零删除）；不可达 → 对照 PASS（fail-open）+
  诊断 SKIP。整改后聚焦三文件：不可达 55P+1 已知 RED+1 SKIP；可达 55P+2 命名 RED。

## 7. 整改后字节

整改提交（普通后继提交）包含：revocation/guards/support 三文件（Redis 归属+精确键）、本目录
修订文件、RUN_LOG §九。整改后四文件工作树 sha256 于提交时再次记录；聚焦运行绑定该字节。
