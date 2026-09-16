# Skill Package Spec

本文描述 Chat Marketplace 的用户技能包 JSON 格式，适用于 `skills/chat/<skill-id>/<lang>.json`。`<lang>` 当前支持 `cn` 和 `en`，文件中的 `id` 必须和父目录 `<skill-id>` 一致。Codex 执行类技能使用 `skills/codex/<skill-id>/SKILL.md` 目录结构，不进入本规范和 Chat `packages.json`，见 [Codex 执行类技能](./CODEX_SKILLS.md)。

## Required Fields

- `schemaVersion`: current value is `1.0`
- `id`: stable kebab-case identifier
- `version`: semantic version
- `name`: localized name, usually `{ "cn": "...", "en": "..." }`
- `description`: localized short task-focused description
- `category`: broad category
- `launch`: where the skill starts
- `instructions`: prompt or instruction source
- `model`: model preferences and candidate restrictions
- `tools`: built-in tool declarations
- `toolServers`: Tool Server requirements
- `permissions`: declared capability surface
- `release`: publication status

## Tool Rules

Built-in tools are declared in `tools` with reserved ids.

Supported built-in tool ids:

- `web_search`

External tool runtime requirements are declared in `toolServers`. Tool Server is the marketplace and product-level name. A Tool Server can internally use MCP or another protocol, but skill authors should not use protocol names as manifest fields.

Example:

```json
{
  "tools": [
    {
      "id": "web_search",
      "name": {
        "cn": "网页搜索",
        "en": "Web Search"
      },
      "description": {
        "cn": "当模型服务商支持时，使用内置网页搜索能力。",
        "en": "Use model-provider web search"
      },
      "required": false
    }
  ],
  "toolServers": [
    {
      "id": "fetch",
      "name": {
        "cn": "网页抓取",
        "en": "Fetch"
      },
      "transport": "stdio",
      "required": false
    }
  ]
}
```

## Review Rules

- Skills must describe a concrete task, not a vague assistant persona.
- Dependencies must be explicit.
- API keys, tokens, private URLs, and local file paths are forbidden.
- Unsafe system instructions are forbidden.
- If a skill requires a Tool Server, mark it as `required: true`.
- If a skill only benefits from a Tool Server, mark it as `required: false`.

## Discovery Status

Chat should resolve runtime status after installation:

- `ready`: model and required tools are available
- `needs_config`: some configurable dependency is missing
- `unavailable`: required model or runtime is not available
