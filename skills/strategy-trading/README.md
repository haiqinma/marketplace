# 策略交易 / Strategy Trading

## 中文

### 用途

`strategy-trading` 把交易想法转化为可执行的策略规则、风险约束、订单计划和自动化方案。默认只生成计划；只有在真实券商工具可用、风险检查通过且用户明确确认后，才允许进入受控实盘执行。

### 工作模式

- `plan_only`：仅生成策略与待执行计划。
- 模拟模式：通过 `paper-broker` 演练订单和风险流程。
- 实盘模式：通过启用实盘能力的 `qmt-broker` 执行已确认订单。

### 安全边界

实盘前必须检查现金、持仓、订单和订单预演结果。自动化方案必须包含标的范围、单笔限额、最大仓位、止损止盈、日亏损上限、暂停开关和人工确认点。不得把模拟结果描述为真实成交。

## English

### Purpose

`strategy-trading` converts a trading idea into executable rules, risk limits, an order plan, and an automation design. It defaults to planning only and may enter controlled live execution only when a real broker tool is available, risk checks pass, and the user explicitly confirms the trade.

### Operating Modes

- `plan_only`: produce a strategy and pending execution plan only.
- Paper mode: rehearse orders and risk controls through `paper-broker`.
- Live mode: execute confirmed orders through a live-enabled `qmt-broker`.

### Safety Boundary

Before live trading, the Skill must check cash, positions, open orders, and the dry-run result. Automation plans must define instrument scope, per-order limits, maximum position, stop-loss and take-profit rules, daily loss limits, a kill switch, and human confirmation points. Paper results must never be presented as live fills.
