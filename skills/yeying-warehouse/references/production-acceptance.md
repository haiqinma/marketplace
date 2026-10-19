# Warehouse Tool 生产验收

这份清单验证已部署的 Warehouse HTTP Tool 基础闭环。它与调用方类型无关，不要求任何特定客户端或业务系统。

## 前置条件

可以使用环境变量：

```bash
export YEYING_WAREHOUSE_URL="https://warehouse.example.com"
export YEYING_WAREHOUSE_TOOL_TOKEN="<短期、可撤销、限定路径的 Tool credential>"
```

也可以使用默认配置文件 `~/.yeying/skills/warehouse/config.toml`：

```toml
[warehouse]
url = "https://warehouse.example.com"
tool_token = "<短期、可撤销、限定路径的 Tool credential>"
```

配置文件必须使用 `0600` 权限。推荐只在文件中保存 URL，通过环境变量注入 token。两种方式的完整优先级见 [配置约定](configuration.md)。

凭证至少需要：

- `asset:read`
- `asset:write`
- 覆盖测试路径的 `pathPrefixes`
- 未过期且状态为 `active`

不要把 secret 写入仓库、脚本参数、归档或日志。验收路径必须是专门的临时路径，例如 `/personal/tool-acceptance/<日期>-<操作者>.txt`，不能指向现有业务对象。`--list-prefix` 必须位于凭证授权范围内；如果凭证只授权一个既有对象，可以把 `--list-prefix` 设置为该对象的完整路径，并使用该对象原内容验证幂等写入。

## 自动验收

```bash
python3 scripts/warehouse_acceptance.py \
  --path "/personal/tool-acceptance/2026-09-29-operator.txt" \
  --list-prefix "/personal/tool-acceptance/" \
  --trace-id "warehouse-acceptance-2026-09-29"
```

脚本依次验证：

1. catalog 包含 5 个当前 Tool；
2. 对授权空间执行 list；
3. 带 SHA-256 写入测试对象；
4. 同内容重复写入成功，验证幂等；
5. stat 返回相同 checksum；
6. read 返回原始内容和 UTF-8 编码；
7. 所有调用共享 `traceId`。

脚本不会删除测试对象。验收结束后，按 Warehouse 正常对象管理流程处理该测试对象；不要直接修改宿主机存储目录。

## 人工验收

自动验收通过后，再验证：

- 使用无 `asset:read` 的凭证调用 catalog 或 read，得到结构化拒绝；
- 使用不在 `pathPrefixes` 内的路径，得到路径范围拒绝；
- 使用已撤销或过期凭证，得到认证失败；
- 用不同内容写入已存在路径，得到 `OBJECT_EXISTS`；
- 使用旧 `ifMatch` 覆盖，得到 `PRECONDITION_FAILED`；
- 在 Warehouse 审计中按 `traceId` 找到调用主体、Tool、路径、结果和时间；
- 审计中不出现 secret、secret hash 或对象正文。

## 当前生产边界

当前验收只覆盖 5 MiB 以内的小对象。大文件上传会话、删除、复制、批量导入和 MCP Server 不属于当前已上线能力，不能用本验收清单推断已经支持。
