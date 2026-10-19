# 阅读总结

[English](README.md)

### 用途

`reading-summary` 用于把文章、网页或长文本提炼成简洁、结构化的阅读结果。它关注主要论点、关键证据、隐含假设、风险和可执行的后续行动。

### 能力

- 总结文章、网页和长文本。
- 区分核心结论、证据、假设与不确定点。
- 把长内容转换为行动项或复习提纲。
- 在工具可用时使用网页搜索或抓取补充原文。

### 配置

这个 Chat Skill 没有独立的 TOML 或环境文件。不要创建 `~/.yeying/skills/reading-summary/config.toml`；运行时配置来自 Chat 和已安装的 Tool Server。

配置来源如下：

1. **技能包：** [`en.json`](en.json) 声明了 `model.syncGlobalConfig=true`、可选的内置 `web_search` 和可选的 `fetch`。这些是仓库中维护的包默认值。
2. **模型：** 在 Chat 的全局模型设置中选择模型服务商并完成认证。由于启用了 `syncGlobalConfig`，本 Skill 继承全局模型，不维护单独的模型凭证。
3. **内置网页搜索：** 没有 Skill 专用 Key。只有当前模型服务商支持网页搜索且 Chat 已启用该能力时才可用。
4. **Fetch Tool Server：** 从 Marketplace 工具目录或 Chat 工具管理页安装 `fetch`。运行环境需要 Python 和 `uvx`；服务定义见 [`../../tools/servers/fetch.json`](../../tools/servers/fetch.json)。该工具没有 API Key 配置项。

模型和 Tool Server 的安装配置由 Chat 管理，具体本地存储位置属于客户端实现，不是本 Skill 契约的一部分。凭证应通过客户端配置界面或认可的密钥存储录入，不得提交到本目录。

### 边界

当原文不可访问或信息不足时，应明确说明缺失内容，不得编造原文观点、证据或引用。
