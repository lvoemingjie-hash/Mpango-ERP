# DC-12R1-MVP-L1-J1-H2-A-R2-V4 — Frozen-Harness Genuine UI Browser Final Report

- 日期：2026-08-22（+08:00）
- 执行者：Zcode
- 裁决：**PASS_DC12R1_MVP_L1_J1_H2_A_R2_V4_OPENCODE_FROZEN_UI_BROWSER_FINAL**
- Candidate（全程字节不变）：`bf574cf9b061f7897eb68cbe92a82ce1201e49f0`
  （git tree `83eb1b09…` 冻结前/运行后/交付一致；tracked 工作区 0 脏；
  backend/** 与 frontend/** 未触碰；.secrets.baseline 字节不变）
- Protected baseline：`origin/product-dev-recovered` = `c5b66d26…`（未变）
- Accepted Kilo source review：`573a288d…`（引用，未改动）
- V3 诊断证据：`45b10060…` 分类为 **UI_FUNCTIONAL_BUT_NOT_MERGE_GRADE_EVIDENCE**
  （历史保留，不重写；其教训——运行后脱敏与多轮规格修补——即 V4 冻结规程的由来）
- 报告分支：`reports/dc12r1-mvp-l1-j1-h2-a-r2-v4-opencode-frozen-ui-browser-final-2026-08-22`

## 冻结协议执行（P2）

1. 规格重写：**全部口令/凭据来自环境变量**；提交的 spec 含**零真实且零占位
   口令字面量**（J00 节点对缺失 env 凭据 fail-closed：任何必需变量为空即红）。
2. spec 与 config 于运行前提交（freeze commit `e2be8825`）：
   - spec git blob `9c2e2bf105eea611eac79c6a9d10974258aa181c`
   - config git blob `74dd70171ce1b103af9556fee6f1799a4c3838e5`
3. 权威运行执行的就是这些精确提交 blob（原位执行，无复制/脱敏/编辑）：
   磁盘字节 == blob 字节在**执行前**与**执行后**各验证一次，全部 MATCH
   （见 hash_proof.md）。
4. 无调试端点、无临时产品源码改动；token 仅从任务自有 maildir 于浏览器外读取。

## 权威运行结果（P5）

**19/19 passed，0 failed，0 skipped，0 flaky，0 interrupted**——单次权威运行，
workers=1，retries=0，无 grep/shard，18.8s。原始 JSON/JUnit、节点 CSV（真实
时长）、节点清单与 reconciliation（清单==运行==通过，失败集为空）均在
`docs/ai-reports/review/evidence/j1-h2a-r2-v4/`。

节点构成：J00 冻结凭据门 + J01–J18（V3 全部真实 UI 合同保留）。

## P4 陈旧会话修正（J14）

在持有真实上下文会话（J09 登录的 retailer1）的浏览器上下文中，完成供应商码
UI 全路径直到**注册提交**：lookup-code 预览 → 显式确认 → 填表 → 提交 →
Registration complete。请求观测：

- `/wholesalers/lookup-code` 与 `/retailers/register` 两类请求**均发生**；
- 每个公共请求 **Authorization presence=false**（仅布尔，值永不采集）；
- 本旅程恰好 **1 个 register POST**；
- 注册完成且只读后置核对（W1 列表）该电话**恰好 1 条绑定**；
- 全程无任何 API helper 参与旅程。

## 覆盖保留确认（P3）

J01 登录/侧栏导航/邀请创建；J04 复制/分享 fragment 链接（剪贴板逐字节）；
J05 新上下文注册；J07 email 必填 + 零密码输入；J08 setup 页 + 门户登录；
J10/J11 供应商码预览/确认/注册；J12 中性未知/畸形 + 零 register；J13 精确
`?w=` + 零裸链接；J15 OS 级双击恰好 1 POST/1 绑定；J16 跨租户精确 401；
J17 UI 停用 + 后续精确 401；J18 390px 交互 + 无横向溢出。

## 工件规范化披露

仓库 pre-commit 的 end-of-file-fixer 为权威 JSON 与 JUnit 追加了标准的
文件末尾换行（仅此一处空白差异；其余字节与运行输出一致）。冻结的
spec/config 不受影响（其 blob 前后哈希 MATCH 独立证明）。

## 卫生与清单（P7/P8）

- Scoped detect-secrets（只读使用候选 baseline）：新证据 0 命中；baseline 未再生成未修改。
- git diff --check 干净；全部证据严格 UTF-8、无 BOM、无 mojibake。
- Manifest 仅覆盖 V4 报告 delta 的非 manifest 提交文件（POSIX 相对路径、稳定
  排序、committed blob 字节 SHA-256、排除自身）；detached 验证
  **missing=0 / extra=0 / mismatch=0**。delta 文件数与 manifest 条目数分别报告于交付。
- 证据目录不含：中止运行、.env、凭据、maildir、身份、SECRET_KEY、token、
  Authorization 值、trace、.secrets.baseline。
