---
name: community-warehouse-skill
description: Evaluate and implement YeYing Warehouse Tool, MCP, Skill, and Agent integrations with clear ownership, scoped authorization, structured contracts, and auditable runtime boundaries. Use when Warehouse needs to expose source materials, object storage, asset APIs, quota state, or WebDAV/S3 capabilities to model clients or Agents.
---

# Warehouse Tool/Agent 化

## 目标

把 Warehouse 的原始资料、对象存储、资产 API、WebDAV/S3、配额和身份边界转换成可被 Chat、Agent 或其他模型客户端安全调用的 Tool，并在确有长生命周期、隔离工作区或异步执行需求时，接入 Agent Runtime。

不要把“Warehouse 支持大模型”理解成 Warehouse 自行调用模型、承载知识加工或运行长期 Agent。Warehouse 是原始资料和对象数据面；Knowledge 负责知识、记忆、Context、检索和 Provenance；Agent 负责长期运行。

## 固定分层

- Warehouse API：对象、目录、空间、权限、配额、事务和错误的最终来源。
- Tool：一项稳定、结构化、可审计的业务能力。
- MCP：发现、描述和调用 Tool 的协议；不是权限系统，也不是 Agent。
- Skill：面向用户的任务入口和运行配置；不是 Tool 或后台进程。
- Agent：拥有实例、工作区、任务生命周期、重试、诊断和工具装配的运行控制面。
- Node：社区应用、Tool、Skill、Agent 的发布目录和授权入口。
- Router：模型渠道、额度、计量和模型凭证治理。

具体职责以社区统一文档和 Warehouse 仓库为准。跨产品概念沉淀到社区文档，不用 `community-product-skill` 汇总多个产品；Router、Knowledge、Node 等产品需要落地时分别创建 `community-router-skill`、`community-knowledge-skill`、`community-node-skill`。

## 工作流程

1. 读取 Warehouse 的 README、源码、路由、配置、OpenAPI 和现有 docs，列出已实现能力、规划能力和历史命名。
2. 明确 Warehouse 与 Knowledge、Router、Node、Agent 的边界；禁止通过 Tool 复制另一产品的数据库或业务状态机。
3. 选择接入形态：
   - 稳定对外能力：HTTP + OpenAPI。
   - 模型客户端需要发现多个能力：在现有 API 之上增加 MCP 适配。
   - 长任务、隔离工作区、安装升级、进程守护：由 Agent Runtime 承担。
   - 简单用户任务入口：由 Chat Skill 承担。
4. 为每个 Tool 定义名称、输入输出 schema、权限 scope、错误码、副作用、幂等、确认要求、超时和异步语义。
5. 让调用身份、资源范围和授权有效期进入请求上下文；权限必须由拥有业务事实的目标产品最终校验。
6. 先实现一条真实、低风险的只读或可回滚闭环，再增加写入、删除、移动、分享等高风险能力。
7. 增加 `requestId`、`traceId`、调用主体、资源、结果、耗时和拒绝原因审计；为超时和重试定义机器可判断的结果。
8. 如需新增或重命名 Codex 执行类 Skill，按 `community-<product-slug>-skill` 命名；不得用 `product`、`general`、`all` 等泛 scope 合并多个产品。
9. 更新 Warehouse 文档，并把“当前已实现”和“后续规划”分开描述。

## Tool 设计硬约束

- 名称使用 `<product>.<resource>.<action>`，表达业务动作，不暴露表名或内部函数名。
- 输入输出必须是结构化 JSON Schema；错误必须包含稳定 code，不能要求调用方解析自然语言。
- 读操作默认无副作用；写、删、移、分享和权限变更必须说明确认、幂等和并发策略。
- 长任务返回 `taskId` 或 `runId`，提供状态、取消、重试和最终结果查询。
- 不向模型、浏览器或第三方 Tool 传递钱包私钥、用户主密码、全局管理员密钥或长期无限范围凭证。
- MCP Server 不得直接访问数据库或存储目录，不得实现与目标产品不一致的第二套权限判断。
- Tool 暂不可用时，调用方必须明确降级结果，不得伪造已完成。

## Warehouse 默认路线

Warehouse 第一批只读 Tool 已通过 HTTP Tool 入口映射现有资产 API：

- `warehouse.space.list` → `GET /api/v1/public/assets/spaces`
- `warehouse.object.list` → `GET /api/v1/public/assets/objects`
- `warehouse.object.stat` → `GET /api/v1/public/assets/object`
- `warehouse.object.read` → `GET/HEAD /api/v1/public/assets/object/content`

写入 Tool 仍需要先补齐 scoped credential、条件写入、幂等键、checksum、异步上传和审计查询，再开放：

- `warehouse.object.put`
- `warehouse.object.copy`
- `warehouse.object.delete`
- `warehouse.upload.create`
- `warehouse.upload.complete`

Knowledge 负责资料加工、检索、Context、证据、Provenance 和 Agent Run；Warehouse 不新增这些业务模型。

## 交付检查

完成前检查：

- 是否能指出最终事实源和权限裁决者？
- 是否复用了现有 API，而不是复制业务逻辑？
- Tool schema、错误、幂等、超时和副作用是否明确？
- 是否限制了身份、目录、动作和有效期？
- 是否有真实调用示例和自动化测试？
- 文档是否没有把规划能力写成已上线？

需要 Warehouse Tool 契约模板和示例时，读取 [references/tool-contract.md](references/tool-contract.md)。
