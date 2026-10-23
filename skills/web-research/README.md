# Web Research

[简体中文](README_CN.md)

### Purpose

`web-research` develops a search plan around the user's question, gathers evidence from multiple sources, and produces structured findings that remain traceable to their sources.

### Capabilities

- Break a research question into a practical search scope.
- Use available web search and fetch tools.
- Compare multiple sources and preserve source references.
- Distinguish facts, inferences, disagreements, and uncertainties.

### Configuration

This Chat Skill has no standalone local configuration file. Its runtime configuration comes from the package manifest, Chat's global model settings, and optional Tool Servers.

Configuration sources:

1. **Skill package:** [`cn.json`](cn.json) declares `model.syncGlobalConfig=true`, optional built-in `web_search`, optional `fetch`, and optional `brave-search`.
2. **Model and built-in search:** configure the model provider in Chat's global model settings. Built-in `web_search` is usable only when the chosen provider exposes it and Chat enables it.
3. **Fetch:** install the `fetch` Tool Server from Marketplace/Tool Management. It requires Python and `uvx`, has no secret fields, and is defined in [`../../tools/servers/fetch.json`](../../tools/servers/fetch.json).
4. **Brave Search:** install `brave-search` from Marketplace/Tool Management, then set `braveApiKey`. Obtain the key from the [Brave Search API dashboard](https://api-dashboard.search.brave.com/login). The launcher passes the stored value to the server as `BRAVE_API_KEY`; users should configure the field in Chat rather than exporting it manually. Node.js and `npx` are required. See [`../../tools/servers/brave-search.json`](../../tools/servers/brave-search.json).

All tools are optional. The Skill can still organize user-supplied sources without them, but it must report that it could not independently search or fetch missing material.

### Boundaries

Conclusions must match the strength of the evidence. When sources are inaccessible, outdated, or contradictory, the Skill must say so and must not fabricate citations or present inference as fact.
