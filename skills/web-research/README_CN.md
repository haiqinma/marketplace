# 网页调研

[English](README.md)

### 用途

`web-research` 围绕用户的问题制定检索方案，收集多个来源的证据，并输出结构化、可追溯的结论。

### 能力

- 拆解研究问题和检索范围。
- 使用可用的网页搜索与抓取工具。
- 比较多个来源并保留来源线索。
- 明确区分事实、推断、分歧和不确定点。

### 配置

这个 Chat Skill 没有独立的本地配置文件。运行时配置来自技能包清单、Chat 全局模型设置和可选的 Tool Server。

配置来源如下：

1. **技能包：** [`cn.json`](cn.json) 声明了 `model.syncGlobalConfig=true`、可选的内置 `web_search`、可选的 `fetch` 和可选的 `brave-search`。
2. **模型与内置搜索：** 在 Chat 全局模型设置中配置模型服务商。只有所选服务商提供网页搜索且 Chat 已启用时，内置 `web_search` 才可用。
3. **Fetch：** 从 Marketplace 或工具管理页安装 `fetch` Tool Server。它需要 Python 和 `uvx`，没有密钥字段，定义见 [`../../tools/servers/fetch.json`](../../tools/servers/fetch.json)。
4. **Brave Search：** 从 Marketplace 或工具管理页安装 `brave-search`，然后填写 `braveApiKey`。API Key 从 [Brave Search API 控制台](https://api-dashboard.search.brave.com/login) 获取。启动器会把客户端保存的值作为 `BRAVE_API_KEY` 传给服务；用户应在 Chat 中配置，不需要手工导出环境变量。运行环境需要 Node.js 和 `npx`。完整定义见 [`../../tools/servers/brave-search.json`](../../tools/servers/brave-search.json)。

所有工具都是可选项。未安装工具时仍可整理用户直接提供的资料，但必须明确说明无法独立搜索或抓取缺失来源。

### 边界

结论应与证据强度匹配。无法访问来源、来源过时或来源互相冲突时，必须明确说明，不得伪造引用或把推断写成事实。
