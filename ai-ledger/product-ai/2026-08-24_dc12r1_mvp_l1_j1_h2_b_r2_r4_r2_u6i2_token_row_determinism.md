# DC-12R1-MVP-L1-J1-H2-B-R2-R4-R2 — U6I2 Token 行身份确定性闭合

- 日期：2026-08-24（+08:00）；执行者：Zcode
- 分支：`zcode/dc12r1-mvp-l1-j1-h2-b-r2-r4-r2-u6i2-token-row-determinism-2026-08-24`
  （自 `3a7ba12ebd6e70444484c3303fc0730ddc19571f`）
- 范围：**恰 2 文件**——`backend/tests/test_u6i2_owner_credential_setup_token_issue.py`
  与本台账。`async_test_utils.py`、产品代码、模型、migration、依赖、前端、
  部署文件与 parent 字节一致（R2-R4-R1 三文件零改动）。
- 背景：CTO 裁决确认 R2-R4-R1 全量唯一红节点为**既有测试确定性缺陷**
  （以 `created_at` 行位推断身份，事务时间戳可并列）。R2-R4-R1 helper
  修复冻结保留。

## 1. 修复合同逐项落实

1. 移除全部 `rows[0]/rows[1]` 多 token 位置断言（模块内已无任何位置索引
   断言；单 token 用元组解包 `(row,) = rows` 强化恰一性）。
2. 新增 `_prior_and_new_rows(rows, prior_raw, new_raw)`：按 `token_hash`
   身份匹配，返回 (prior_row, new_row)。
3. 集合等价断言 `set(by_hash) == {prior_hash, new_hash}`：证明集合**恰好**
   是 prior 与 newly-issued 两枚（非仅数量），并有 token_hash 去重守卫。
4. 状态按身份断言：expired 场景——prior `used_at is None`、
   `revoked_at is not None`（产品合同：发行新 token 时
   `_close_expired_tokens` 吊销过期 prior）、`expires_at <= now`；
   new——`used_at/revoked_at is None`、`expires_at > now`。
   used/revoked 参数化场景——prior 对应字段按参数断言非空/为空。
5. `_unexpired_active_token_count == 1` 产品合同断言原样保留。
6. `_token_rows` 排序改为 `ORDER BY created_at, id` 稳定全序（id 为 UUID
   PK 总序键）；**身份断言不依赖任何排序**，UUID 次序不被解释为创建时间。
7. `created_at` 模型/server_default/发行实现零改动。
8. 无 sleep、无重复运行、无放宽断言、无条件通过。

## 2. 真实性门禁

| 门 | 结果 |
|---|---|
| 纯测试级反例：`test_prior_and_new_identity_matching_is_order_independent` 以两种排列（含反向）过身份匹配 | GREEN（两种排列均绿） |
| 位置断言突变（helper 体替换为 rows[0]/rows[1]）→ 反例节点 | **确定性 RED**（1 failed）→ 字节还原 → **GREEN** |
| 模块自然序 / 反向序 | 15/15 + 15/15 |
| 原失败节点连续 50 次受控负载（4 worker / 16 CPU） | **50/50** |

## 3. 联动门禁与全量

栈 A/B 全新（PG16-alpine 15561/15562 + Redis7-alpine 16561/16562，全新卷，
alembic 037，autovacuum=on，非超级用户 h2btester）：

| 门 | 结果 |
|---|---|
| U6I2 模块自然序 / 反向序（Stack A） | 15/15 + 15/15 |
| R2-R4-R1 helper 模块（Stack A） | 27/27 + 27/27 |
| focused bundle | 恰收集 109；自然 109/109；反向节点 109/109 |

**权威全量（最终工作树字节，每栈重置后恰一次）：**

| 栈 | collected | passed | failed | errors | skipped | xfailed | xpassed | gap |
|---|---|---|---|---|---|---|---|---|
| A | 3764 | 3701 | **0** | **0** | **48** | **15** | **0** | **0** |
| B | 3764 | 3701 | **0** | **0** | **48** | **15** | **0** | **0** |

- 3764 = 3763（R2-R4-R1 基线）+ 1 个新反例测试。
- skip 节点+原因集、xfail 节点+原因集 **A/B 完全一致**；计数全等。
- 全量后每栈仅存 `test_r2_full_<s>` 一个库；`dc11t2fr_%` 临时角色 0。

## 4. 裁决

```
STOP_AND_REPORT_CTO_AWAITING_KILO_AND_INDEPENDENT_ZERO_RED
```

本轮为**候选证据**：即使作者双栈全绿，仍需 Kilo 对
`218be690..最终 SHA` 的累计有界审查，及 OpenCode 独立双栈最终门禁，
方可进入 merge review。本任务不启动 Kilo/浏览器/合并/部署。
