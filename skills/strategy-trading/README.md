# Strategy Trading

[简体中文](README_CN.md)

### Purpose

`strategy-trading` converts a trading idea into executable rules, risk limits, an order plan, and an automation design. It defaults to planning only and may enter controlled live execution only when a real broker tool is available, risk checks pass, and the user explicitly confirms the trade.

### Operating Modes

- `plan_only`: produce a strategy and pending execution plan only.
- Paper mode: rehearse orders and risk controls through `paper-broker`.
- Live mode: execute confirmed orders through a live-enabled `qmt-broker`.

### Safety Boundary

Before live trading, the Skill must check cash, positions, open orders, and the dry-run result. Automation plans must define instrument scope, per-order limits, maximum position, stop-loss and take-profit rules, daily loss limits, a kill switch, and human confirmation points. Paper results must never be presented as live fills.
