# 策略交易

[English](README.md)

### 用途

`strategy-trading` 把交易想法转化为可执行的策略规则、风险约束、订单计划和自动化方案。默认只生成计划；只有在真实券商工具可用、风险检查通过且用户明确确认后，才允许进入受控实盘执行。

### 工作模式

- `plan_only`：仅生成策略与待执行计划。
- 模拟模式：通过 `paper-broker` 演练订单和风险流程。
- 实盘模式：通过启用实盘能力的 `qmt-broker` 执行已确认订单。

### 配置

这个 Chat Skill 不读取 Skill 专用 TOML。包默认值位于 [`cn.json`](cn.json) 和 [`en.json`](en.json)，模型服务商和 Tool Server 的实际值在 Chat 中配置。

#### 模型

清单使用 `model.syncGlobalConfig=false` 并提供保守的生成参数。模型服务商账号和可用模型仍来自 Chat 的模型设置；任何模型服务商 API Key 都不应写入本仓库。

#### 必需的 iFinD 数据工具

从 Marketplace 或工具管理页安装 `ifind-data`，运行环境需要 Node.js 和 `npx`。

- `refreshToken` 为必填项，从 [iFinD/QuantAPI 账号详情页](https://quantapi.10jqka.com.cn/gwstatic/static/ds_web/super-command-web/index.html#/AccountDetails) 获取。
- `accessToken` 可选；不填写时连接器使用 `refreshToken` 换取访问令牌。
- `baseUrl` 可选，默认是 `https://quantapi.51ifind.com/api/v1`。
- `requestTimeoutMs` 可选，默认是 `30000`。

Chat 保存这些工具字段，并仅在启动连接器进程时映射为 `IFIND_REFRESH_TOKEN`、`IFIND_ACCESS_TOKEN`、`IFIND_BASE_URL` 和 `IFIND_REQUEST_TIMEOUT_MS`。定义见 [`../../tools/servers/ifind-data.json`](../../tools/servers/ifind-data.json)。

#### 可选的模拟券商

安装 `paper-broker` 用于模拟交易。在工具管理页配置 `initialCash`、`market`、`currency`、`allowShort` 和 `requireConfirmation`。这些是本地模拟设置，不是真实券商凭证。默认值和环境映射见 [`../../tools/servers/paper-broker.json`](../../tools/servers/paper-broker.json)。

#### 可选的 QMT 实盘券商

`qmt-broker` 仅支持 Windows，需要本机安装 MiniQMT、`xtquant`、Node.js 和 `npx`。配置项如下：

- `qmtUserdataPath`：从本机 MiniQMT 安装目录取得 `userdata_mini` 路径。
- `accountId`：从券商或 QMT 账号中取得资金账号。
- `accountType`：通常为 `STOCK` 或 `CREDIT`。
- `pythonCommand`：安装了 `xtquant` 的 Python 命令。
- `enableLiveTrading`：账号和风控验证完成前保持 `false`。
- `requireConfirmation`：建议保持开启，让 `place_order` 必须传入 `confirmed=true`。

完整定义见 [`../../tools/servers/qmt-broker.json`](../../tools/servers/qmt-broker.json)。不要把券商账号、Token 或其他敏感配置写入技能清单、README 或仓库。

### 安全边界

实盘前必须检查现金、持仓、订单和订单预演结果。自动化方案必须包含标的范围、单笔限额、最大仓位、止损止盈、日亏损上限、暂停开关和人工确认点。不得把模拟结果描述为真实成交。
