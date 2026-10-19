# Strategy Trading

[简体中文](README_CN.md)

### Purpose

`strategy-trading` converts a trading idea into executable rules, risk limits, an order plan, and an automation design. It defaults to planning only and may enter controlled live execution only when a real broker tool is available, risk checks pass, and the user explicitly confirms the trade.

### Operating Modes

- `plan_only`: produce a strategy and pending execution plan only.
- Paper mode: rehearse orders and risk controls through `paper-broker`.
- Live mode: execute confirmed orders through a live-enabled `qmt-broker`.

### Configuration

This Chat Skill does not read a Skill-specific TOML file. The package defaults are in [`en.json`](en.json), while model-provider and Tool Server values are configured in Chat.

#### Model

The manifest uses `model.syncGlobalConfig=false` and supplies conservative generation parameters. The selected provider account and model availability still come from Chat's model settings; no provider API key belongs in this repository.

#### Required iFinD Data Tool

Install `ifind-data` from Marketplace/Tool Management. It requires Node.js and `npx`.

- `refreshToken` is required. Obtain it from the [iFinD/QuantAPI Account Details page](https://quantapi.10jqka.com.cn/gwstatic/static/ds_web/super-command-web/index.html#/AccountDetails).
- `accessToken` is optional; when omitted, the connector exchanges `refreshToken` for an access token.
- `baseUrl` is optional and defaults to `https://quantapi.51ifind.com/api/v1`.
- `requestTimeoutMs` is optional and defaults to `30000`.

Chat stores these Tool fields and maps them to `IFIND_REFRESH_TOKEN`, `IFIND_ACCESS_TOKEN`, `IFIND_BASE_URL`, and `IFIND_REQUEST_TIMEOUT_MS` only for the connector process. See [`../../tools/servers/ifind-data.json`](../../tools/servers/ifind-data.json).

#### Optional Paper Broker

Install `paper-broker` for simulation. Configure `initialCash`, `market`, `currency`, `allowShort`, and `requireConfirmation` in Tool Management. These are local simulation settings, not real brokerage credentials. The defaults and environment mapping are defined in [`../../tools/servers/paper-broker.json`](../../tools/servers/paper-broker.json).

#### Optional QMT Live Broker

`qmt-broker` supports Windows only and requires a locally installed MiniQMT, `xtquant`, Node.js, and `npx`. Configure:

- `qmtUserdataPath`: obtain the `userdata_mini` directory from the local MiniQMT installation.
- `accountId`: obtain the broker fund-account ID from the broker/QMT account.
- `accountType`: normally `STOCK` or `CREDIT`.
- `pythonCommand`: the Python executable where `xtquant` is installed.
- `enableLiveTrading`: keep `false` until account and risk controls are verified.
- `requireConfirmation`: keep enabled so `place_order` requires `confirmed=true`.

See [`../../tools/servers/qmt-broker.json`](../../tools/servers/qmt-broker.json). Never place brokerage account details or tokens in the Skill manifest, README, or repository.

### Safety Boundary

Before live trading, the Skill must check cash, positions, open orders, and the dry-run result. Automation plans must define instrument scope, per-order limits, maximum position, stop-loss and take-profit rules, daily loss limits, a kill switch, and human confirmation points. Paper results must never be presented as live fills.
