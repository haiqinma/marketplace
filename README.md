# Chat Marketplace

这是 Chat 应用使用的社区市场仓库。

本仓库维护 Chat 可发现、可安装、可配置的社区能力包，包括技能、工具、模型服务商和后续存储能力。产品层统一使用“技能、工具、模型、存储”四层术语；MCP 只作为工具层当前主要协议和具体实现方式出现。

同时，本仓库的 `skills/codex/` 维护 Codex 执行类技能，用于沉淀社区工程协作、产品 Tool 化、Agent 化等可复用工作方法。Codex 技能采用 `SKILL.md` 目录结构，不进入 Chat 当前加载的 `packages.json`。

## 产品模型

技能是用户选择的任务入口。技能声明：

- 这个技能解决什么任务
- 使用什么 instructions 或系统指令
- 需要什么模型能力
- 可以使用哪些内置工具或 Tool Server
- 运行前需要用户配置什么
- 面向用户展示的名称、描述和工具依赖名应支持中英文

工具能力单独配置：

- 内置工具是模型服务商提供的能力，例如 OpenAI Web Search。
- Tool Server 是外部工具运行时，例如 Brave Search、Fetch、Git、Filesystem。
- OpenAPI 导入是 HTTP API 描述，后续可以适配成 Tool Server。

后续市场可以继续扩展：

- Tool：外部工具运行时或连接器，名称、描述和配置说明应支持中英文
- Model Provider：模型服务商接入说明和能力声明
- Storage：存储能力和知识库能力
- Finance / Trading：策略交易、模拟执行和券商连接器

## 仓库结构

```txt
skills/
  chat/                  Chat 应用使用的用户技能包
    <skill-id>/
      cn.json            中文版本，可选
      en.json            英文版本，可选
  codex/                 Codex 执行类技能，不进入 Chat packages.json
tools/
  servers/               Tool Server 包定义
  packages/              社区维护的 Tool Server 源码包
  index.json             由脚本生成的工具轻量索引
  packages.json          由脚本生成的工具包列表
providers/               预留：模型服务商发布包
schemas/
  skill.schema.json      单个技能包的 JSON Schema
  tool-server.schema.json 单个 Tool Server 包的 JSON Schema
templates/
  skill.json             技能包起始模板
  tool-server.json       Tool Server 包起始模板
docs/
  SKILL_SPEC.md          技能编写与审核规则
  CODEX_SKILLS.md        Codex 执行类技能说明
  PUBLISH_FLOW.md        技能发布、上线、配置与使用流程
index.json               由脚本生成的技能轻量索引，作为发布清单提交
packages.json            由脚本生成的技能包列表，供 Chat 当前版本加载
scripts/
  build.mjs              校验并生成技能和工具发布清单
```

当前 `scripts/build.mjs` 处理 `skills/chat/` 下的 Chat 技能包和 `tools/servers/` 下的 Tool Server 包。`providers/` 后续应增加对应 schema 和发布清单生成逻辑。

## 添加技能

1. 创建 `skills/chat/<skill-id>/`，复制 `templates/skill.json` 为 `skills/chat/<skill-id>/<lang>.json`，例如 `skills/chat/web-research/cn.json`。
2. 填写任务定义、模型偏好、内置工具、Tool Server 依赖和开场白。
3. 运行：

```bash
node scripts/build.mjs
```

4. 提交 Pull Request。

## 发布流程

技能作者通过 Pull Request 发布技能包。

维护者重点审核：

- 技能名称是否清晰、聚焦
- 描述是否能让用户判断使用场景
- 是否包含隐藏密钥或私有接口
- 是否存在不安全的提示词注入
- 模型和工具需求是否明确
- Tool Server 依赖是否显式声明，而不是隐式假设

合并后，Chat 应用当前加载技能包地址：

```txt
https://raw.githubusercontent.com/yeying-community/marketplace/main/packages.json
```

Chat 应用当前加载工具包地址：

```txt
https://raw.githubusercontent.com/yeying-community/marketplace/main/tools/packages.json
```

社区维护的 Tool Server 源码包位于 `tools/packages/`。如果工具声明通过 `npx -y @yeying-community/<package>` 启动，需要通过 GitHub Actions 发布到 npm。仓库 secret 使用 `npm_token`，workflow 是 `Publish Tool Packages`。

## Chat 集成

Chat 应用当前应该加载：

- 本地内置技能包列表：`/skill-packages.json`
- 远程社区技能包列表：本仓库的 raw `packages.json`
- 远程工具包列表：本仓库的 raw `tools/packages.json`

加载后，Chat 可以在发现页展示远程技能和工具。用户点击安装时，应用通过 `skillPackageToSkill()` 把技能包转换成本地技能，并保存到用户的技能库。

完整流程见：`docs/PUBLISH_FLOW.md`。
