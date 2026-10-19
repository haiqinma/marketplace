---
name: community-warehouse-skill
description: Use YeYing Warehouse's generic, scoped, auditable object capabilities for listing spaces, inspecting metadata, reading objects, and writing small objects through the stable HTTP Tool contract.
---

# Warehouse 通用对象能力

## 目标

提供 Warehouse 的空间、对象、权限、配额和完整性能力。调用方可以是任意应用、自动化程序或其他系统；本 skill 不绑定调用方类型，也不负责调用方的任务、会话、知识或运行生命周期。

## 固定分层

- Warehouse API：对象、目录、空间、权限、配额、事务和错误的最终来源。
- Tool：一项稳定、结构化、可审计的 Warehouse 业务能力。
- MCP：可选的发现、描述和调用协议；不是权限系统。
- 调用方：使用 HTTP Tool 的任意应用或自动化程序。
- Warehouse：对象内容、元数据、权限、配额、条件写入和审计的最终事实源。

调用方自己的业务关联和生命周期由调用方维护；Warehouse 不保存调用方的任务或会话状态。

## 工作流程

1. 读取 Warehouse 的 README、源码、路由、配置、OpenAPI 和现有 docs，列出已实现能力、规划能力和历史命名。
2. 明确 Warehouse 只负责对象和资产事实；禁止通过 Tool 复制其他系统的数据库或业务状态机。
3. 选择接入形态：
   - 稳定对外能力：HTTP + OpenAPI。
   - 需要发现多个能力：在现有 API 之上增加 MCP 适配。
4. 为每个 Tool 定义名称、输入输出 schema、权限 scope、错误码、副作用、幂等、确认要求、超时和异步语义。
5. 让调用身份、资源范围和授权有效期进入请求上下文；权限必须由拥有业务事实的目标产品最终校验。
6. 先实现一条真实、低风险的只读或幂等写入闭环，再增加删除、移动、分享等高风险能力。
7. 增加 `requestId`、`traceId`、调用主体、资源、结果、耗时和拒绝原因审计；为超时和重试定义机器可判断的结果。
8. 更新 Warehouse 文档，并把“当前已实现”和“后续规划”分开描述。

## Tool 设计硬约束

- 名称使用 `<product>.<resource>.<action>`，表达业务动作，不暴露表名或内部函数名。
- 输入输出必须是结构化 JSON Schema；错误必须包含稳定 code，不能要求调用方解析自然语言。
- 读操作默认无副作用；写、删、移、分享和权限变更必须说明确认、幂等和并发策略。
- 长任务返回 `taskId` 或 `runId`，提供状态、取消、重试和最终结果查询。
- 不向模型、浏览器或第三方 Tool 传递钱包私钥、用户主密码、全局管理员密钥或长期无限范围凭证。
- MCP Server 不得直接访问数据库或存储目录，不得实现与目标产品不一致的第二套权限判断。
- Tool 暂不可用时，调用方必须明确降级结果，不得伪造已完成。

## Warehouse 当前能力

## 认证配置

配置加载顺序为：命令行 `--config`、`YEYING_WAREHOUSE_CONFIG`、默认文件 `~/.yeying/skills/warehouse/config.toml`。环境变量 `YEYING_WAREHOUSE_URL`、`YEYING_WAREHOUSE_TOOL_TOKEN` 和 `YEYING_WAREHOUSE_UPLOAD_DIRECTORY` 会覆盖 TOML 中的同名字段；完整约定见 [配置约定](references/configuration.md)。

当前 HTTP Tool 入口使用 Warehouse 的用户态 Bearer JWT。安装 Skill 不会自动获得登录身份，调用方必须在运行环境中显式提供：

```bash
export YEYING_WAREHOUSE_URL="http://localhost:6065"
export YEYING_WAREHOUSE_TOOL_TOKEN="<短期 scoped Tool credential>"
```

`YEYING_WAREHOUSE_URL` 是 Warehouse 服务根地址。无人值守调用使用 `YEYING_WAREHOUSE_TOOL_TOKEN`；交互式验证可临时使用 `YEYING_WAREHOUSE_TOKEN`。凭证只通过 `Authorization: Bearer ...` 发送，不得写入仓库、归档、命令历史或日志；客户端也不得打印请求头。

当前认证边界：

- Warehouse WebDAV AK/SK 只用于 WebDAV，不可直接调用 HTTP Tool。
- Warehouse S3 AK/SK 需要 S3 Signature V4，不可直接填入 `YEYING_WAREHOUSE_TOKEN`。
- 其他系统的 AK/SK 或内部服务凭证不具备 Warehouse 资产访问权限。
- Warehouse 已支持短期、可撤销、限制用户/路径/动作/有效期的 Tool credential。无人值守调用应使用 `YEYING_WAREHOUSE_TOOL_TOKEN`，避免长期保存用户 JWT。

本 Skill 提供的 `scripts/warehouse_tool.py` 可用于验证和自动化调用。它支持 Tool catalog、通用 call，以及 `put`、`put-file`、`read`、`list`、`stat` 快捷操作；`put-file` 可把明确指定的本地文件写入配置的远端默认目录，或写入命令行给出的完整 Warehouse 路径。认证失败、权限拒绝、冲突和超限会以非零退出码返回。`scripts/warehouse_acceptance.py` 用于对已部署服务执行非破坏性的生产冒烟检查。

Warehouse 资产 Tool 已通过 HTTP Tool 入口映射现有资产 API：

- `warehouse.space.list` → `GET /api/v1/public/assets/spaces`
- `warehouse.object.list` → `GET /api/v1/public/assets/objects`
- `warehouse.object.stat` → `GET /api/v1/public/assets/object`
- `warehouse.object.read` → `GET/HEAD /api/v1/public/assets/object/content`
- `warehouse.object.put` → `PUT /api/v1/public/assets/object/content`

`warehouse.object.put` 允许模型在凭证授权路径内直接写入不超过 5 MiB 的 UTF-8 或 base64 对象，`confirmationRequired=false`。默认只创建；同路径同内容重试成功，不同内容返回冲突。覆盖必须显式传 `overwrite=true`，并可用 `ifMatch` 防止并发覆盖。Warehouse 最终执行身份、路径、UCAN、配额和 checksum 校验。

需要保存现场资料时，调用方可以使用 `warehouse.object.put` 写入文本、结构化 JSON、日志或 manifest；对象格式和业务关联由调用方自行定义。Warehouse 只负责按授权路径保存对象，不判断对象是否属于某类会话或任务。

大文件和其他写入能力仍需要补齐上传任务幂等、异步状态和审计查询后再开放：

- `warehouse.object.copy`
- `warehouse.object.delete`
- `warehouse.upload.create`
- `warehouse.upload.complete`

资料加工、检索、业务关联和运行状态由调用方负责；Warehouse 不新增这些业务模型。

## 交付检查

完成前检查：

- 是否能指出最终事实源和权限裁决者？
- 是否复用了现有 API，而不是复制业务逻辑？
- Tool schema、错误、幂等、超时和副作用是否明确？
- 是否限制了身份、目录、动作和有效期？
- 是否有真实调用示例和自动化测试？
- 文档是否没有把规划能力写成已上线？

需要 Warehouse Tool 契约模板和示例时，读取 [references/tool-contract.md](references/tool-contract.md)。
