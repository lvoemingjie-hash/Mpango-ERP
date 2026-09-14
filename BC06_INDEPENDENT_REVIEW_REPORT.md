# BC-06 独立评审报告

**EXECUTOR = Kilo**
**日期：** 2026-09-14
**候选：** `1ee75d9f`（"test(sku): isolate BC06 schemas and owned sessions"）
**树：** `5712eb85e6bf76d8662a6bb7890e609d09bd7ec0`
**分支：** `codexl/dc-12r1-mvp-l1-sku-delivery-r2-fixture-isolation-2026-09-12`

---

## 1. 起点核实

| 项目 | 登记值 | 实际值 | 结论 |
|------|--------|--------|------|
| 候选提交 | `1ee75d9f` | `1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e` | 匹配 |
| 树哈希 | `5712eb85` | `5712eb85e6bf76d8662a6bb7890e609d09bd7ec0` | 前缀匹配 |
| 归属分支 | `codexl/dc-12r1-mvp-l1-sku-delivery-r2-fixture-isolation-2026-09-12` | 包含该提交 | 匹配 |

起点确认无误。评审在全新隔离工作树 `C:\Users\Jeff0\kilo_bc06_independent_review_wt`（detached HEAD at `1ee75d9f`）中展开，未复用任何历史工作树或 ZCode-W 遗留文件。

---

## 2. F1 复跑结果

**测试文件：** `backend/tests/test_sku_bc06_reprice_guard.py`
**测试节点总数：** 37 items（28 个函数 + parametrize 展开）

| 状态 | 数量 | 说明 |
|------|------|------|
| **passed** | **35** | 核心 BC-06 业务逻辑全部通过 |
| **failed** | **2** | 环境配置问题，与 BC-06 业务逻辑无关 |
| **skipped** | **0** | — |

**完整运行验收状态：** 未通过（35 PASS、2 环境失败；需修复环境配置后方可完整通过）

### 失败节点根因分析

**`test_bc06_fixture_preserves_unrelated_connections[same_role]`**
- **根因：** 测试假设 `bc06r1` 数据库用户**不是**超级用户（`rolsuper = false`），断言 `NOT (rolsuper OR pg_has_role(...))`。
- **实际角色证据：**
  ```sql
  SELECT rolname, rolsuper FROM pg_roles WHERE rolname IN ('bc06r1', 'reporting_user');
  -- 结果：bc06r1 | t（超级用户）
  --       reporting_user | f
  ```
  在本次复跑的新建容器中，`bc06r1` 被创建为超级用户（`rolsuper = true`），导致断言 `assert not True` 失败。
- **性质：** 环境疏漏（test fixture 与容器初始化假设不一致），非 BC-06 业务逻辑缺陷。

**`test_bc06_fixture_preserves_unrelated_connections[reporting_role]`**
- **根因：** 测试硬编码了 `REPORTING_DATABASE_URL` 中 `reporting_user` 的密码，但迁移 `011_s6_p_reporting_role.py` 使用环境变量 `REPORTING_USER_PASSWORD` 创建该用户。在本次复跑中，未设置该环境变量，迁移使用默认值创建用户，导致密码不匹配、认证失败。
- **认证错误证据：**
  ```
  asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "reporting_user"
  ```
- **性质：** 环境疏漏（测试凭证与迁移凭证源不一致），非 BC-06 业务逻辑缺陷。

**结论：** 核心 BC-06 业务逻辑（37 节点中的 35 个）在全新任务栈上复跑通过，结果稳定。2 个失败均源于测试环境初始化配置，可通过统一凭证源修复。

---

## 3. 源码审查：实现 vs 测试断言对照

### 3.1 审查范围

- **`backend/repositories/pricing_repository.py`**（124 行，来源 50f15ded）
- **`backend/services/package_identity.py`**（226 行，来源 50f15ded）
- **`backend/tests/test_sku_bc06_reprice_guard.py`**（1779 行，37 个测试节点）

### 3.2 实现逻辑梳理

**`pricing_repository.py` 三条路径：**
1. `get_price` — 单 retailer+sku 当前价格查询
2. `get_prices_bulk` — 批量查询，空列表返回空 dict
3. `set_price` — **R2-R1 改动路径**：调用 `lock_sku_row`，若返回 None 则抛结构化 404；否则 upsert retailer_prices 行

**`package_identity.py` 四条路径：**
1. `lock_sku_row` — **R2-R1 改动路径**：`FOR UPDATE + populate_existing`，显式过滤 `is_deleted IS FALSE`，返回锁定后的最新行或 None
2. `package_quantity_changed` — Decimal 精确比较，None 视为未变更
3. `has_identity_use_history` — 顺序探测四张表（order_items / inventory_movements / inventory_stocks / inventory_reservations）
4. `ensure_package_quantity_change_allowed` — 三个顺序门控：历史锁 → 价格数据完整性 RED → 当前价格配置 REPRICE_REQUIRED

### 3.3 测试覆盖映射

| 测试节点 | 覆盖的实现路径 | 断言内容 |
|----------|---------------|----------|
| `test_all_sku_creation_entries_create_zero_retailer_price_rows` | 创建路径 | 五种 SKU 创建方式均不产生 retailer_prices |
| `test_zero_value_stock_placeholder_is_not_use_and_does_not_block` | `has_identity_use_history` → inventory_stocks | 零值占位符不触发历史锁 |
| `test_repackage_without_history_or_price_succeeds_via_both_entries` | `ensure_package_quantity_change_allowed` | 无历史无价格时双入口均成功 |
| `test_same_value_repackage_is_never_blocked_even_with_live_price` | `package_quantity_changed` | 同值更新不触发门控 |
| `test_live_price_blocks_both_entries_with_zero_data_change` | 价格门 + 双入口 | 实时价格返回 409，零数据变更 |
| `test_only_soft_deleted_price_rows_do_not_gate_and_stay_byte_identical` | 价格门 + is_deleted 过滤 | 软删除价格行不阻止，字节不变 |
| `test_any_live_price_among_multiple_retailers_blocks` | 价格门 | 多零售商中任意活跃行即阻止 |
| `test_corrupt_nonpositive_live_price_fails_closed_red` | 价格数据完整性 RED | 非正数/ NULL 价格 fail-closed |
| `test_concurrent_price_first_then_repackage_returns_reprice_required` | `lock_sku_row` FOR UPDATE 序列化 | 12 轮并发 price-first 均返回 409 |
| `test_concurrent_repackage_first_then_set_price_targets_new_definition` | `set_price` + 序列化 | repackage 先提交后 set_price 成功 |
| `test_transaction_history_locks_repackage_immutable_after_use` | `has_identity_use_history` → order_items | stable/linked_legacy/legacy 三种订单引用均锁定 |
| `test_history_lock_dominates_the_price_gate` | 门控优先级 | 历史锁优先于价格门 |
| `test_soft_deleted_order_items_still_lock_repackage` | `has_identity_use_history` → order_items is_deleted | 软删除订单行仍锁定 |
| `test_any_inventory_movement_locks_repackage` | `has_identity_use_history` → inventory_movements | 任意 movements 行锁定 |
| `test_nonzero_on_hand_stock_locks_repackage` | `has_identity_use_history` → inventory_stocks | 非零 on_hand 锁定 |
| `test_nonzero_reserved_stock_locks_repackage` | `has_identity_use_history` → inventory_stocks | 非零 reserved 锁定 |
| `test_reservation_status_locks_repackage` | `has_identity_use_history` → inventory_reservations | reserved/consumed/released 三种状态均锁定 |
| `test_locked_fresh_read_after_concurrent_commit` | `lock_sku_row` + populate_existing | 预加载陈旧对象后，锁内读取最新值 |
| `test_update_sku_syncs_sibling_fields_and_preserves_package_quantity` | `update_sku` 兄弟同步 | 重命名同步到所有 unit，各自 package_quantity 不变 |
| `test_concurrent_soft_delete_wins_updater_returns_structured_404` | `lock_sku_row` 软删除过滤 | 三入口（sku/unit/set_price）并发软删除均返回 404 |
| `test_reverse_linearization_update_wins_then_soft_delete` | 反向线性化 | updater 先提交，随后软删除，两者均持久化 |
| `test_set_price_fail_closed_on_missing_or_soft_deleted_sku` | `set_price` + `lock_sku_row` | 缺失/软删除 SKU 返回 404，零价格写入 |

---

## 4. 发现的验证盲区

以下盲区是 **本次独立评审新增的发现**，F1 测试未覆盖：

### 盲区 A：`set_price` 缺少价格有效性自验证（低风险）

**实现事实：**
`pricing_repository.py:set_price`（第 68–124 行）**直接写入 `price` 参数，不验证 `price > 0` 或 `price is not None`**。

**实际调用链：**
- 产品端唯一调用者 `PUT /prices`（`api/v1/pricing.py`）通过 `SetPriceRequest` 接收请求，其中 `price: Decimal = Field(..., gt=0, le=Decimal("999999.99"))` 且自定义校验器 `validate_positive` 确保 `v > 0`，因此正常 HTTP 请求不会携带无效价格进入 `set_price`。
- 数据库层存在 `ck_retailer_prices_positive_price CHECK (price > 0)` 及 `price NOT NULL` 约束，即使应用层绕过，数据库也会拒绝。

**残余风险：**
- `set_price` 作为 repository 函数，可能被其他内部调用者直接调用而跳过 API 层校验。若未来迁移删除 CHECK 约束，`set_price` 将成为唯一的失效保护层，且其抛出的将是数据库 IntegrityError 而非结构化的 `PRICE_DATA_INTEGRITY_RED`。

**后续建议（不阻塞交付）：**
- 在 `set_price` 中增加对 repository 直接调用的防御性校验：当 `price is None or price <= 0` 时返回结构化的 `PRICE_DATA_INTEGRITY_RED` 错误。
- 注意：无效请求应统一由 API 层的 `SetPriceRequest` 拦截并返回 422；仅对表示**既有脏数据**的场景（如绕过 API 直接操作数据库后残留的非法行）才应触发 `PRICE_DATA_INTEGRITY_RED`。

**测试现状：** F1 测试中 `test_corrupt_nonpositive_live_price_fails_closed_red` 验证的是 **package_quantity 修改入口** 的 RED 行为，**未验证直接 `set_price` 写入无效价格时的行为**。

### 盲区 B：`updated_by` 审计字段处理不一致（待办）

**实现事实：**
- **更新现有行**（第 111–112 行）：`if updated_by: existing.updated_by = updated_by` — 仅当传入非 None 时才更新
- **创建新行**（第 120 行）：`created_by=updated_by` — 总是赋值，允许 NULL

**唯一产品调用者：**
`api/v1/pricing.py:set_retailer_price`（第 144–150 行）始终传入 `updated_by=UUID(token.user_id)`，即非 None 的 UUID。因此当前生产路径下，更新和创建的审计字段行为一致。

**风险定性：**
- 当前生产路径下风险较低，因为唯一调用者始终提供有效 UUID。
- 若未来有内部调用者直接调用 `set_price(updated_by=None)`，则存在审计追踪断层风险。

**不采纳的默认修法：**
- **不采纳**“缺少操作人时清空旧审计字段”的方案。因为 `if updated_by` 的语义是“仅在有操作人意图时刷新审计字段”，而非“无操作人时主动清除”。

**后续改进前提：**
- 若需改进，应先明确无操作人调用的合法场景，再决定是保持现状、增加防御性日志，还是统一赋值语义。

**测试现状：** F1 测试中所有 `set_price` 调用均传入 `updated_by=None`，但断言仅检查 404/409 状态码和 package_quantity，**未验证审计字段的实际写入值**。

### 盲区 C：`get_price` / `get_prices_bulk` 在 BC-06 隔离上下文中未覆盖（低风险）

**实现事实：**
- `get_price` 和 `get_prices_bulk` 在其他测试文件（`test_phase3_pricing.py`）中有覆盖
- 但在 BC-06 隔离审查范围内，**没有验证这两个函数在 tenant schema 隔离、软删除过滤等 BC-06 特定场景下的行为**

**测试现状：** F1 测试完全不涉及这两个读取路径。

### 盲区 D：并发 `set_price` 场景未直接测试（低风险）

**实现事实：**
- `lock_sku_row` 使用 `FOR UPDATE`，理论上两个并发 `set_price` 会序列化
- 但 F1 测试中的并发场景只覆盖了 **price vs repackage** 和 **repackage vs soft-delete**

**测试现状：** 没有两个连接同时调用 `set_price` 的测试。

### 盲区 E：`has_identity_use_history` 的 `sku_code` 防御性处理缺失（低风险）

**实现事实：**
- SQL 查询中 `sku_code = :sku_code` 使用参数化绑定，无注入风险
- 该处使用参数化原始 SQL，`= NULL` 不会自动重写为 `IS NULL`；传入 `sku_code=None` 时不会触发意外的 NULL 匹配，但也不会得到有意义的查询结果

**测试现状：** 所有调用均传入合法的非空 `sku_code`。

### 盲区 F：`lock_sku_row` 的 `sku_id` 类型安全无防御（低风险）

**实现事实：**
- 函数签名 `lock_sku_row(db: AsyncSession, *, sku_id)` 缺少类型注解
- SQLAlchemy 会在运行时检查类型，错误类型会抛出 `StatementError`

**测试现状：** 未测试错误类型输入。

---

## 5. 独立源码复核及运行验证结果

**结论：本次独立评审完成了对 BC-06 核心路径的独立源码复核，并进行了部分运行验证，列明以下未覆盖项。**

**已完成的工作：**

1. **审查起点完全独立：** 从候选 `1ee75d9f` 新建工作树，未复用 ZCode-W 的任何历史工作树或缓存文件。所有文件读取均为首次接触。

2. **核心路径独立源码复核：**
   - `lock_sku_row` 的 R2-R1 改动（排除软删除行 + 返回结构化 404）在三入口（sku/unit/set_price）均有并发测试覆盖
   - `set_price` 的锁依赖和 fail-closed 行为已测试
   - `package_quantity_changed` 的同值不阻止逻辑已测试
   - `has_identity_use_history` 的四表探测逻辑已通过参数化测试覆盖

3. **部分运行验证：** 在全新 PostgreSQL 容器上复跑 F1，35/37 通过，2 个失败为环境配置问题。

**未覆盖项（独立评审边界）：**

1. **盲区 A（set_price 缺少价格有效性自验证）：** 发现 `set_price` 自身不验证价格有效性，依赖 API 层 `SetPriceRequest` 的 `gt=0` 校验和数据库 CHECK 约束。当前生产路径下风险低，但 repository 直接调用场景缺乏防御。
2. **盲区 B（updated_by 处理不一致）：** 发现更新路径的条件赋值与创建路径的无条件赋值不一致。当前唯一产品调用者始终传入有效 UUID，但未测试 `updated_by=None` 的场景。
3. **盲区 C（get_price / get_prices_bulk 在 BC-06 隔离上下文中未覆盖）：** 读取路径在 BC-06 特定场景下未验证。
4. **盲区 D（并发 set_price 场景未直接测试）：** 没有两个连接同时调用 `set_price` 的测试。
5. **盲区 F（lock_sku_row 的 sku_id 类型安全无防御）：** 未测试错误类型输入。

**独立性说明：**
- 本次评审完成了独立源码复核和部分运行验证。
- 独立性不等于穷尽全部缺陷：以上未覆盖项为评审边界内发现的潜在风险，不代表这些路径在真实场景下必然失败。
- 如果我是完全未参与原始设计的人来写测试，我会多写：
  - 直接调用 `set_price` 写入 `Decimal("-1")` 和 `Decimal("0")`，验证是否 fail-closed 或被静默接受（虽然 DB 约束会阻止，但应用层应提供更友好的错误）
  - 调用 `set_price(updated_by=None)` 后，读取 retailer_prices 行验证 `created_by`/`updated_by` 的实际写入值
  - 两个连接并发调用 `set_price`（同一 retailer+sku），验证序列化后的最终价格值
  - `get_prices_bulk([])` 在 tenant schema 中的返回值

---

## 6. 最终结论与建议

### 6.1 交付判定

| 维度 | 评估 |
|------|------|
| F1 复跑稳定性 | 35 PASS、2 环境失败；完整运行验收未通过 |
| 核心业务逻辑覆盖 | 充分（R1/R2/R2-R1 三条路径均有测试） |
| 盲区风险 | **A 低风险、B 待办** |
| 独立评审充分性 | 完成独立源码复核及部分运行验证，列明未覆盖项 |

### 6.2 交工后处理建议（不阻塞当前交付）

以下两项建议作为技术债记录，由 Codex-L / ZCode-W 在后续迭代中处理：

1. **盲区 A 补丁方向：** 在 `set_price` 中增加对 repository 直接调用的防御性校验。当 `price is None or price <= 0` 时返回结构化的 `PRICE_DATA_INTEGRITY_RED` 错误。注意：正常 HTTP 请求由 `SetPriceRequest` 的 `gt=0` 校验拦截并返回 422；`PRICE_DATA_INTEGRITY_RED` 仅用于表示**既有脏数据**场景，不用于替换普通请求校验。

2. **盲区 B 补丁方向：** 当前唯一产品调用者 `api/v1/pricing.py:set_retailer_price` 始终传入 `UUID(token.user_id)`，生产路径下风险低。后续若改进，应先明确无操作人调用的合法场景，再决定是保持现状、增加防御性日志，还是统一赋值语义。**不采纳**“缺少操作人时清空旧审计字段”的默认修法。

### 6.3 证据效力

本报告可作为 **"BC-06 核心路径已完成独立源码复核及部分运行验证"** 的证据，直接附进给 CTO 的最终交工材料。评审过程满足以下独立性要求：
- 全新隔离工作树
- 未复用 ZCode-W 历史环境
- 独立执行 F1 复跑
- 独立阅读源码并形成判断

**声明：** 本次独立评审完成了源码复核和部分运行验证，并列明未覆盖项。独立性不等于穷尽全部缺陷；以上未覆盖项为评审边界内发现的潜在风险，不代表这些路径在真实场景下必然失败。

---

*报告生成时间：* 2026-09-14
*评审执行者：* Kilo
