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

### 配置与边界

默认配置文件是 `~/.yeying/skills/warehouse/config.toml`。调用方必须提供 Warehouse 服务地址和短期、可撤销、限定路径与动作的 Tool credential。Skill 不保存调用方的任务或会话状态，不复制其他产品的数据库或权限系统，也不得把钱包私钥、用户密码、管理员密钥或长期无限范围凭证传给模型或第三方工具。
