# DC-12R1-MVP-L1-J1-H2-A-R2-V4-E1 — Evidence Truth Correction

- 日期：2026-08-22（+08:00）
- 模式：docs/evidence-only；无浏览器重跑；无产品/冻结件修改
- 基报告 tip：`8617b1132f78d499fe17ae2f2466ba7c4c0feb9c`
- E1 delta：恰好 3 个文件（修改 V4 最终报告、新增本文件、重建 manifest）。

## 修正 1 — 范围记账

- `bf574cf9..8617b113` 总 delta = **14 个文件**（13 个非 manifest 证据/报告
  文件 + manifest 自身）。
- manifest 覆盖全部 13 个非 manifest 文件；manifest 排除自身。
- 既有 detached 验证（missing=0 / extra=0 / mismatch=0）有效。
- E1 后累计记账：**总 delta 15 个文件，manifest 14 条，manifest 排除自身**。

## 修正 2 — 冻结规格注释纠正（不改动已执行规格）

`v4-frozen-ui.spec.ts` 第 17–18 行注释称 APIRequestContext 的使用仅为
"READ-ONLY GET 后置条件"。实际事实：J14 与 J15 的后置条件在执行只读
GET `/retailers` 之前，还使用 `POST /auth/login` 与
`POST /auth/select-tenant` **仅为取得 W1 上下文授权令牌**。

- 这些 POST 不执行任何零售商注册旅程动作（旅程全部由浏览器 UI 完成），
  符合任务书"API 仅可置备 + 只读后置条件"的精神与 J15 条款的明示允许；
- 但旧注释字面过宽（"only READ-ONLY GET"），与实际不完全一致。
- 处置：记录为本注释纠正；**不重写已执行的冻结规格**（其 blob 与哈希
  证明链保持不变——P2 冻结完整性优先于注释措辞）。

## 修正 3 — 凭据措辞纠正

J18 在门户登录表单输入了固定探针串 `viewport-probe-input`（仅用于 390px
视口下已渲染表单的溢出测量交互；**该输入从未被提交**——无 Sign In 点击，
且它不是任何账户的有效运行时凭据，无法通过认证）。

因此将报告中"零真实且零占位口令字面量"的表述更正为：

> **零真实或可登录凭据字面量；所有用于成功认证的凭据均由环境注入。**

（环境注入的口令：W1_PASSWORD、R1/R2/R3_PASSWORD，均不存在于任何提交
文件；J18 探针串为非认证 UI 探针。）

## E1 后完整性声明

候选源码、冻结 spec/config、authoritative JSON/JUnit、node CSV、
reconciliation、清理证据在 E1 前后保持**字节一致**（blob 对比证明见
交付记录）；仅 V4 最终报告措辞、本 E1 文档与 manifest 属 E1 delta。
