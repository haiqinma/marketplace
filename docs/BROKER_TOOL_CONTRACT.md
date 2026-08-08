# Broker Tool 契约

本文定义策略交易 skill 需要的 broker connector 最小能力。生产目标是接入真实券商；模拟券商只用于开发验证和演练，不应被包装成生产实盘能力。

## 连接器类型

- `live broker`：真实券商或交易柜台连接器，例如 QMT / miniQMT / PTrade / IBKR / Futu。可以真实下单，必须启用风控、确认和审计。
- `paper broker`：模拟交易连接器，只能验证策略、工具链路和交互流程，不能真实下单。
- `data provider`：行情、财务、公告、选股等数据源，例如同花顺 QuantAPI / iFinD。它不是 broker，不能承担下单职责。当前 marketplace 中对应 `ifind-data`。

## 工具列表

### `broker_status`

查询连接器状态、执行模式和安全约束。模型和 Chat 必须先用它判断当前能力边界，再决定是否进入模拟、实盘前检查或实盘执行。

输入：

- `checkConnection`：可选，是否真实检查本地 broker 连接。默认不检查，避免状态页或普通对话意外拉起本地交易环境。

输出：

- `connectorType`：`live` 或 `paper`
- `provider`：连接器名称，例如 `qmt` 或 `paper-broker`
- `tradingMode`：`plan_only`、`simulation`、`dry_run_only` 或 `live`
- `configured`：必要配置是否存在
- `connected`：连接状态；未检查时可为空
- `liveTradingEnabled`：是否允许真实下单
- `requireConfirmation`：`place_order` 是否要求 `confirmed=true`
- `account`：脱敏后的账号和环境摘要
- `capabilities`：支持的工具能力列表
- `safety`：实盘、确认和风控说明

### `dry_run_order`

校验订单但不提交。

输入：

- `symbol`：标的代码
- `side`：`buy` 或 `sell`
- `quantity`：数量
- `orderType`：`market` 或 `limit`
- `limitPrice`：限价单价格，可选

输出：

- `accepted`：是否通过校验
- `reason`：拒绝原因，可选
- `estimatedCashImpact`：预计资金影响
- `estimatedPositionImpact`：预计持仓影响

### `place_order`

提交订单。实盘 connector 必须要求上游显式确认后才允许执行。

输入：

- `symbol`
- `side`
- `quantity`
- `orderType`
- `limitPrice`
- `clientOrderId`

输出：

- `orderId`
- `status`
- `submittedAt`

### `cancel_order`

撤销未完成订单。

输入：

- `orderId`

输出：

- `orderId`
- `status`

### `query_orders`

查询订单。

输入：

- `status`：可选
- `symbol`：可选

输出：

- `orders`

### `query_positions`

查询持仓。

输入：

- `symbol`：可选

输出：

- `positions`

### `query_cash`

查询资金。

输出：

- `cash`
- `currency`
- `available`

## 安全规则

- `broker_status` 必须可在不泄露密钥、不泄露完整账号的情况下返回状态。
- `broker_status` 默认不应强制连接真实 broker，除非调用方传入 `checkConnection=true`。
- 默认只允许 `dry_run_order`，除非用户显式启用真实下单。
- 实盘 `place_order` 必须依赖用户显式确认。
- 实盘 connector 必须暴露是否启用真实下单的配置，例如 `enableLiveTrading`。
- connector 必须返回订单 ID 和状态，不能只返回成功文本。
- connector 必须暴露资金、持仓和订单查询能力，便于 skill 做执行前后校验。
- connector 不应把密钥写进 marketplace 包；密钥只能由用户运行时配置。

## 自动化执行规则

- 自动化方案属于 skill，自动化执行能力属于 broker tool。
- 没有 broker tool 时，skill 只能输出 `plan_only`。
- 只有 `paper-broker` 时，skill 只能进入 `paper_run`，不能声称已经实盘。
- 真实 broker 的 `liveTradingEnabled=false` 时，只允许 `dry_run_order` 和查询类能力。
- 从 `precheck` 进入 `armed` 必须有用户明确确认。
- 从 `armed` 调用 `place_order` 必须带 `confirmed=true`，并记录 `clientOrderId` 或等价审计 ID。
- 任一风控条件失败、连接失败、用户暂停或 kill switch 触发时，应进入 `paused` 或 `error`。
