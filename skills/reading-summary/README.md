# Reading Summary

[简体中文](README_CN.md)

### Purpose

`reading-summary` turns articles, web pages, and long-form text into concise, structured reading notes. It focuses on the main argument, key evidence, assumptions, risks, and practical next steps.

### Capabilities

- Summarize articles, web pages, and long text.
- Separate conclusions, evidence, assumptions, and uncertainties.
- Convert lengthy material into action items or review notes.
- Use web search or fetch tools to retrieve source material when available.

### Configuration

This Chat Skill does not use a standalone TOML or environment file. Do not create a `~/.yeying/skills/reading-summary/config.toml`; runtime configuration comes from Chat and the installed Tool Servers.

Configuration sources:

1. **Skill package:** [`en.json`](en.json) declares `model.syncGlobalConfig=true`, optional built-in `web_search`, and optional `fetch`. These are package defaults maintained in this repository.
2. **Model:** select and authenticate a model provider in Chat's global model settings. Because `syncGlobalConfig` is enabled, the Skill follows that global model instead of maintaining a separate model credential.
3. **Built-in web search:** no Skill-specific key exists. It is available only when the selected model provider supports web search and the capability is enabled in Chat.
4. **Fetch Tool Server:** install `fetch` from the Marketplace tool catalog or Chat's tool-management screen. It requires Python and `uvx`; its server definition is [`../../tools/servers/fetch.json`](../../tools/servers/fetch.json). It has no API-key fields.

Chat owns the installed model and Tool Server settings. Their on-disk location is client-specific and is not part of this Skill contract. Credentials must be entered through the client configuration UI or its approved secret store, not committed to this directory.

### Boundaries

When the source is unavailable or incomplete, the Skill must state what is missing and must not invent claims, evidence, or citations.
