# DC-12R1-MVP-L1-J1-H2-A-R2-M1 — Controlled Merge Report

- 日期：2026-08-22（+08:00）
- 裁决：**PASS_DC12R1_MVP_L1_J1_H2_A_R2_CONTROLLED_MERGE**
- Merge SHA：`6e9470a1daa5d6eece29724316fdd8aef6b737c1`
- TARGET（P1）：`c5b66d26b83a0cc6170282de1e2fe281e448b2a8`
- SOURCE（P2）：`bf574cf9b061f7897eb68cbe92a82ce1201e49f0`
- SOURCE_PARENT：`78f888759df85be52ba0ec7e6f5cbbaa190d4ef3`（核验一致）
- 浏览器证据：`26cad662ea398eb2afc4ee69741715dbae890b8c`（V4-E1，未重跑）
- Kilo source review：`573a288d346fb78b26ccd0636028148c0f39ecad`
- Kilo evidence review：`560617977893390e8d39259ae1b97ed25478186b`
- MAIN（未触碰）：`134ea59e02204842e55ebe36f721f44df5a33737`

## 抄写差异披露（KILO_SOURCE_REVIEW 字符串）

任务书给出的 KILO_SOURCE_REVIEW 字符串为 **39 个十六进制字符**
（`...602814c0f39ecad`）——真实 SHA 为 40 字符
`573a288d346fb78b26ccd0636028148c0f39ecad`，二者前 30 字符相同，任务
字符串恰在第 31 位丢失一个 `8`。全仓唯一匹配该 30 字符前缀的对象即
上述真实 SHA（Kilo R2-V1 source review，PASS），且其所在报告分支 tip
在 V3/V4/E1 各任务中均验证为该精确 SHA。**结论：无任何 ref 移动，
差异为任务文本单字符抄写脱漏**，据此继续执行而非 STOP。

## 证明门（全部通过）

- `origin/product-dev-recovered` == TARGET ✓；source 分支 tip == SOURCE ✓；
  browser-evidence == `26cad662…` ✓；main == `134ea59e…` ✓；两个 Kilo
  报告分支 tip 均为各自冻结 SHA ✓。
- TARGET 是 SOURCE 祖先 ✓；`SOURCE^` == SOURCE_PARENT ✓。
- `TARGET..SOURCE` 累计 delta == **41 文件** ✓。
- `manifest_sha256_h2a_r2.txt`：**40 条**、排除自身、从 committed blob
  字节复算 missing=0 / extra=0 / mismatch=0 ✓。
- 漂移筛查：delta 中无 migration（alembic/versions）、无依赖/lockfile
  （package.json/pnpm-lock/requirements/pyproject）、无部署路径
  （docker-compose/k8s/nginx/Dockerfile）变更 ✓。

## 合并结构（全部满足）

- 命令：仅 `git merge --no-ff --no-edit bf574cf9`；无 squash/rebase/
  cherry-pick/amend/历史重写。
- 合并 commit 恰好两个父亲：P1 == TARGET、P2 == SOURCE ✓。
- 合并树与 SOURCE **字节一致**：tree 对象 ID 相同
  （`83eb1b09c6eea7145b3d5069323ee2ffb54cc63d`）且
  `git diff --exit-code HEAD bf574cf9` 零输出 ✓。
- 零冲突、零手工编辑（工作区干净）✓。

## 合并树门禁（全新任务栈：h2a_m1_pg16@15438 + h2a_m1_redis7@6398，
fresh `test_h2a_m1`，alembic base→037；.venv/node_modules 为指向既有
安装的 junction（工具链复用，零源码改动））

| 门禁 | 结果 |
|---|---|
| H2-A 后端聚焦（8 文件，台账原命令） | **137/137** |
| Contract D TestRangeCap | **8/8** |
| H2-A 前端聚焦（自然序） | **30/30** |
| H2-A 前端聚焦（确定性交替序：文件倒序） | **30/30** |
| 全量前端 Vitest | 26 files / **385/385** |
| `pnpm build` | exit 0 |
| py_compile（全部 delta py） | OK |
| `git diff --check` | 干净 |
| scoped pre-commit（含 detect-secrets） | 全过 |
| UTF-8/无 BOM/mojibake（41 delta 文件） | 全过 |

无 skip/xfail/断言弱化或测试修改；未重跑 Playwright（V4-E1 证据保持权威）。

## 推送与事后证明

- 竞争门：fetch 后六个冻结 ref 全部原样（KILO_SOURCE_REVIEW 见上方披露）
  → 通过。
- 推送：`git push --force-with-lease=refs/heads/product-dev-recovered:<TARGET>`
  `origin HEAD:refs/heads/product-dev-recovered`——快进
  `c5b66d26..6e9470a1`，显式租约守卫（CAS 语义），非 force。
- 事后：`origin/product-dev-recovered` == `6e9470a1…`（本地合并 SHA）✓；
  SOURCE、MAIN、浏览器证据与两个 Kilo 报告 ref 全部不变 ✓。

## 清理（已完成，过去时实况）

- 集成 worktree 的 .venv/node_modules junction 已移除；worktree 已删除
  （`git worktree remove --force`，注册表干净）。
- 容器 `h2a_m1_pg16`、`h2a_m1_redis7` 已 `docker rm -f`；匿名卷随容器
  移除；未创建任务网络；端口 15438/6398 随容器释放。
- 临时合并分支 `m1-merge-at-target` 已删除。
