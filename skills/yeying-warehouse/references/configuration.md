# 配置约定

Warehouse skill 客户端统一支持环境变量和 TOML 配置文件：

```text
命令行 --config > YEYING_WAREHOUSE_CONFIG > ~/.yeying/skills/warehouse/config.toml
```

配置文件示例：

```toml
[warehouse]
url = "http://localhost:6065"
tool_token = ""
upload_directory = "/personal/backups"
```

字段覆盖关系：

| 配置文件 | 环境变量 | 用途 |
| --- | --- | --- |
| `warehouse.url` | `YEYING_WAREHOUSE_URL` | Warehouse 服务根地址 |
| `warehouse.tool_token` | `YEYING_WAREHOUSE_TOOL_TOKEN` | 短期 scoped Tool credential |
| `warehouse.tool_token` | `YEYING_WAREHOUSE_TOKEN` | 交互式兼容凭证 |
| `warehouse.upload_directory` | `YEYING_WAREHOUSE_UPLOAD_DIRECTORY` | `put-file` 未指定远端路径时使用的 Warehouse 目录 |

`YEYING_WAREHOUSE_CONFIG` 可以指定其他 TOML 路径；命令行 `--config` 优先级最高。环境变量覆盖配置文件同名字段。配置文件可以只保存服务地址，把 token 通过环境变量或 Secret Manager 注入。

包含 `tool_token` 的配置文件必须是当前用户可读写，权限不应超过 `0600`。客户端不会打印 token，也不会把配置来源以外的敏感值写入日志。

`upload_directory` 是远端 Warehouse 绝对路径，不是本地目录。调用 `put-file <本地文件>` 时，客户端将本地文件名追加到该目录；也可以给 `put-file` 显式传入完整 Warehouse 对象路径覆盖默认目录。该配置只决定目标路径，不会扩大 Tool credential 的授权范围，最终仍由 Warehouse 校验。

```bash
python3 scripts/warehouse_tool.py put-file ~/.zshrc
```

配置文件、shell 启动文件和其他现场资料可能含有 token、密码或私钥。上传前先检查并脱敏；不要把敏感值放进命令行参数、日志或归档。

其他 skill 应复用相同目录约定：

```text
$HOME/.yeying/skills/<skill-name>/config.toml
```
