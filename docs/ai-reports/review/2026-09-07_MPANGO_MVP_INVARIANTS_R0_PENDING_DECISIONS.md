# MPANGO-MVP-INVARIANTS-R0：待业务合同决定的预期结果（证据保留）

任务指令明确：不自行规定"有付款就绝不能取消"，不自行选择收入确认时点。以下三项外部已复现缺陷**保留证据、不设断言**，等待业务责任人/会计与后端责任人共同决定预期结果后，方可转为断言型回归测试。

## 证据来源（保留，未改动）

- `AI_REPORT_INBOX/external-architecture-2026-09-06/counterexamples.json`
  - `cancel_after_concurrent_committed_payment`：state=cancelled，payment_amount=100.00
  - `route_confirmation_ledger` = {}；`after_40_cash_on_100_order` = {}；`after_full_100_cash` = {receivable:-100, cash:+100}
- `AI_REPORT_INBOX/external-architecture-2026-09-06/supplementary-probes.json`
  - `uncollected_credit_order_full_return`：outstanding_after_return=100.00，cash_ledger_change=-100.0000，cash_received=0

上述为外部审查在其专用实验库（PostgreSQL 16、基线 bd2373cb）的真实运行结果；相关源码定位本轮已在基线逐一核对（见任务报告第 3/6 节）。

## 1. 取消撞收款

**现状机制**：取消路由先无锁预读订单，用旧状态决定是否释放预留（orders.py:1012），随后无锁调用 `crud.cancel_order`（crud/order.py:495，仅按内存状态校验）；收款入口持订单行锁提交（orders.py:712）。交错结果：已收款 100 的 confirmed 单变为 cancelled，payments/ledger 不变，预留释放逻辑基于旧状态。

**待业务决定**：
1. 已收部分款（0<收<整单）的订单：允许取消吗？若允许，已收款如何处置（原路退回 / 转预收 / 转应收）？
2. 已收全款未履约：允许取消吗？现金流与应收/预收如何表述？
3. 已履约订单是否只能走退货（退货语义同样待定，见 3）？
4. 取消被拒绝时，用户可见的错误与重试路径是什么（与幂等/超时恢复联动）？

## 2. 部分现金未入账 与 确认时点

**现状机制**：确认入口（orders.py:590）走 CRUD + 预留，不调用 OrderService 的 CONFIRMED 记账分支（order_service.py:282）；PARTIALLY_PAID 不产生任何 ledger；到 PAID 一次性按整单额记 cash/receivable（order_service.py:290-309）。外部时点表：确认后无账簿 → 收 40 后仍无账簿 → 收齐 60 后应收 −100/现金 +100。仓库既有测试 test_s5d5 还将"部分收款后现金账变动为 0"固化为断言。

**待业务决定**：
1. 收入确认时点：确认 / 履约 / 其他控制权转移事件（CTO D04：IFRS 15 以控制权转移为判断依据，预收可能形成合同负债）。
2. "已收现金"是否必须逐笔实时入账（现金事件 vs 结清事件的分离）？
3. 应收账的确认与清偿表达：确认时记应收、每笔收款冲减，还是维持"结清一次性"？
4. test_s5d5 等既有断言随新政策如何修订（不得为修数而改预期）。

## 3. 赊销退货（未收应收冲销 vs 现金退款）

**现状机制**：完整退货固定记 revenue +/cash −（ledger_service.py:319-359，reference_type='refund'），不冲减应收、不清偿绑定 outstanding_balance、不区分"应退"与"实退"。赊销履约进入 PAID 时有意跳过现金结算（order_service.py:294），故 PAID 语义=获准履约而非结清。

**外部已复现结果**：未收现金的 100 赊销单全退 → outstanding_balance 仍 100，现金账 −100（无实际付款的现金流出）。

**待业务决定**：
1. 退货时按原收款方式回溯：现金销售退现金、赊销销售冲应收——是否成立？
2. "应退款 / 实际退款完成"是否需要两个事实（应付客户余额）？
3. 赊销退货是否清偿绑定 outstanding_balance、在哪个事件清偿？
4. 部分退货/部分履约的组合（外部报告 D04 建议样例：交付 100 实收 40 退 60 等）何时纳入。
5. 重复退货的业务唯一标识（每单一次全退？退货单号？）——技术唯一键形态依赖此决定。

## 转为断言测试的前置条件

上述每项由业务责任人给出书面预期（事件表：订单义务/履约/收款/分配/应收/退货/应退/实退）后，按本轮测试的夹具（真实入口 + 两连接确定性屏障）将现状观测改为断言。在此之前，任何一轮都不应把这些行为"测绿"。
