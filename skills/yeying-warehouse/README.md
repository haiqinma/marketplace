# YeYing Warehouse Object Capabilities

[简体中文](README_CN.md)

### Purpose

`yeying-warehouse` provides generic, scoped, and auditable object capabilities for listing spaces, inspecting metadata, reading objects, and writing small objects. Warehouse remains the source of truth for object content, permissions, quotas, integrity, and audit records.

### Current Capabilities

- `warehouse.space.list`: list accessible spaces.
- `warehouse.object.list`: list objects.
- `warehouse.object.stat`: inspect object metadata.
- `warehouse.object.read`: read object content.
- `warehouse.object.put`: write objects up to 5 MiB within an authorized path.

### Configuration

The default file is `~/.yeying/skills/warehouse/config.toml`:

```toml
[warehouse]
url = "https://warehouse.example.com"
tool_token = "<short-lived scoped Tool credential>"
upload_directory = "/personal/agent-uploads"
```

Configuration-file selection, from highest to lowest priority:

1. `--config /absolute/path/config.toml`
2. `YEYING_WAREHOUSE_CONFIG`
3. `~/.yeying/skills/warehouse/config.toml`

Environment overrides:

| TOML field | Environment variable | Meaning |
| --- | --- | --- |
| `warehouse.url` | `YEYING_WAREHOUSE_URL` | Warehouse service origin |
| `warehouse.tool_token` | `YEYING_WAREHOUSE_TOOL_TOKEN` | Preferred short-lived Tool credential |
| `warehouse.tool_token` | `YEYING_WAREHOUSE_TOKEN` | Interactive user-JWT fallback |
| `warehouse.upload_directory` | `YEYING_WAREHOUSE_UPLOAD_DIRECTORY` | Default remote directory for `put-file` |

`upload_directory` is an absolute path inside Warehouse, not a local filesystem directory. It selects a default destination but does not expand the credential's allowed path prefixes.

#### Obtaining a Warehouse Tool credential

Obtain `url` from the deployed Warehouse browser origin or the deployment operator. Then sign in to Warehouse and create a short-lived credential with only the required actions and path prefixes. The credential-management endpoint requires the user's login JWT:

```http
POST /api/v1/public/tools/credentials
Authorization: Bearer <Warehouse login JWT>
Content-Type: application/json

{
  "name": "local-agent",
  "scopes": ["asset:read", "asset:write"],
  "pathPrefixes": ["/personal/agent-uploads/"],
  "expiresAt": "<short expiration timestamp>"
}
```

The response returns the Tool credential secret once. Store that secret as `tool_token` or inject it with `YEYING_WAREHOUSE_TOOL_TOKEN`. Credential management also supports:

```text
GET  /api/v1/public/tools/credentials
POST /api/v1/public/tools/credentials/{id}/rotate
POST /api/v1/public/tools/credentials/{id}/revoke
GET  /api/v1/public/tools/audits?credentialId=<optional>
```

Rotation immediately invalidates the old secret. A Tool credential can call only the asset Tool catalog/call surface; it cannot create other credentials or read credential-management audits. For interactive local verification, `YEYING_WAREHOUSE_TOKEN` may contain a user login JWT, but production Agents should use the scoped Tool credential instead.

WebDAV AK/SK, S3 AK/SK, Node internal credentials, wallet private keys, and credentials from other products are not valid HTTP Tool tokens.

Protect a file containing `tool_token`:

```bash
mkdir -p ~/.yeying/skills/warehouse
chmod 700 ~/.yeying/skills/warehouse
chmod 600 ~/.yeying/skills/warehouse/config.toml
```

Verify with a read-only catalog or list call before writing:

```bash
python3 scripts/warehouse_tool.py catalog
python3 scripts/warehouse_tool.py list /
```

### Boundaries

The Skill does not store caller task or session state, duplicate another product's database or permission system, or expose wallet private keys, user passwords, administrator secrets, or long-lived unrestricted credentials to models or third-party tools. Complete precedence and field details are in [`references/configuration.md`](references/configuration.md).
