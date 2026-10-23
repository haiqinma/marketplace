# 夜莺仓库对象能力

[English](README.md)

### 用途

`yeying-warehouse` 提供通用、限定范围且可审计的对象能力，用于列出空间、查看元数据、读取对象和写入小对象。Warehouse 是对象内容、权限、配额、完整性和审计的最终事实源。

### 当前能力

- `warehouse.space.list`：列出可访问空间。
- `warehouse.object.list`：列出对象。
- `warehouse.object.stat`：读取对象元数据。
- `warehouse.object.read`：读取对象内容。
- `warehouse.object.put`：在授权路径内写入不超过 5 MiB 的对象。

### 配置

默认配置文件是 `~/.yeying/skills/warehouse/config.toml`：

```toml
[warehouse]
url = "https://warehouse.example.com"
tool_token = "<短期 scoped Tool credential>"
upload_directory = "/personal/agent-uploads"
```

配置文件选择优先级从高到低为：

1. `--config /绝对路径/config.toml`
2. `YEYING_WAREHOUSE_CONFIG`
3. `~/.yeying/skills/warehouse/config.toml`

环境变量覆盖关系：

| TOML 字段 | 环境变量 | 用途 |
| --- | --- | --- |
| `warehouse.url` | `YEYING_WAREHOUSE_URL` | Warehouse 服务根地址 |
| `warehouse.tool_token` | `YEYING_WAREHOUSE_TOOL_TOKEN` | 首选的短期 Tool credential |
| `warehouse.tool_token` | `YEYING_WAREHOUSE_TOKEN` | 交互式用户 JWT 兼容入口 |
| `warehouse.upload_directory` | `YEYING_WAREHOUSE_UPLOAD_DIRECTORY` | `put-file` 使用的默认远端目录 |

`upload_directory` 是 Warehouse 内部的绝对路径，不是本地文件系统目录。它只选择默认目标，不会扩大凭证允许访问的路径前缀。

#### 获取 Warehouse Tool credential

`url` 从已部署 Warehouse 的浏览器地址或部署管理员处获取。随后登录 Warehouse，创建只包含所需动作和路径前缀的短期凭证。凭证管理接口需要用户登录 JWT：

```http
POST /api/v1/public/tools/credentials
Authorization: Bearer <Warehouse 登录 JWT>
Content-Type: application/json

{
  "name": "local-agent",
  "scopes": ["asset:read", "asset:write"],
  "pathPrefixes": ["/personal/agent-uploads/"],
  "expiresAt": "<较短的过期时间>"
}
```

响应只返回一次 Tool credential secret。立即把 secret 保存为 `tool_token`，或通过 `YEYING_WAREHOUSE_TOOL_TOKEN` 注入。凭证管理还支持：

```text
GET  /api/v1/public/tools/credentials
POST /api/v1/public/tools/credentials/{id}/rotate
POST /api/v1/public/tools/credentials/{id}/revoke
GET  /api/v1/public/tools/audits?credentialId=<可选>
```

轮换会立即使旧 secret 失效。Tool credential 只能调用资产 Tool catalog/call，不能创建其他凭证或读取凭证管理审计。交互式本地验证可以临时使用包含用户登录 JWT 的 `YEYING_WAREHOUSE_TOKEN`，生产 Agent 应使用 scoped Tool credential。

WebDAV AK/SK、S3 AK/SK、Node 内部凭证、钱包私钥和其他产品的凭证都不能作为 HTTP Tool Token。

保护包含 `tool_token` 的配置文件：

```bash
mkdir -p ~/.yeying/skills/warehouse
chmod 700 ~/.yeying/skills/warehouse
chmod 600 ~/.yeying/skills/warehouse/config.toml
```

写入对象前先执行只读 catalog 或 list 验证：

```bash
python3 scripts/warehouse_tool.py catalog
python3 scripts/warehouse_tool.py list /
```

### 边界

Skill 不保存调用方的任务或会话状态，不复制其他产品的数据库或权限系统，也不得把钱包私钥、用户密码、管理员密钥或长期无限范围凭证传给模型或第三方工具。完整优先级和字段说明见 [`references/configuration.md`](references/configuration.md)。
