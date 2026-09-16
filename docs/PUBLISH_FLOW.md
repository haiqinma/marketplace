# 技能发布、上线、配置与使用流程

本文面向技能作者、维护者和 Chat 集成开发者，说明一个社区技能从提交到用户可用的完整流程。

本仓库是 Chat Marketplace，用于维护技能、工具、模型服务商和存储能力等可发现、可安装、可配置的社区能力。产品层统一使用“技能、工具、模型、存储”四层术语；MCP 只作为工具层当前主要协议和具体实现方式出现。

当前已经落地的是技能发布流程和 Tool Server 工具包发布流程。模型服务商和存储能力先保留扩展方向，后续需要补各自 schema、审核规则和发布清单。

Codex 执行类技能维护在 `skills/codex/`，用于沉淀工程协作和产品落地方法，格式为 `SKILL.md` 目录结构。它们不进入 Chat 当前加载的 `packages.json`，维护规则见 [Codex 执行类技能](./CODEX_SKILLS.md)。

## 1. 流程总览

1. 作者在 `skills/chat/<skill-id>/<lang>.json` 下新增或修改技能包。
2. 作者运行 `npm run check` 生成 `index.json` 和 `packages.json`。
3. 作者提交 Pull Request。
4. 维护者审核技能质量、安全和依赖声明。
5. PR 合并后，`packages.json` 通过 GitHub raw 地址对外发布。
6. Chat 发现页加载远程 `packages.json`。
7. 用户安装技能。
8. Chat 根据技能声明提示用户补齐模型或工具配置。
9. 用户点击技能进入会话或对应工作区。

Tool Server 包流程：

1. 作者在 `tools/servers/` 下新增或修改 Tool Server 包。
2. 作者运行 `npm run check` 生成 `tools/index.json` 和 `tools/packages.json`。
3. 作者提交 Pull Request。
4. 维护者审核运行命令、配置项、安全边界和仓库来源。
5. PR 合并后，`tools/packages.json` 通过 GitHub raw 地址对外发布。
6. Chat 发现页和工具管理页加载远程 `tools/packages.json`。
7. 用户安装并配置工具。
8. 依赖该工具的技能状态从 `needs_config` 变为可用。

## 2. 作者怎么发布技能

复制模板：

```bash
mkdir -p skills/chat/<skill-id>
cp templates/skill.json skills/chat/<skill-id>/cn.json
```

编辑技能包时重点填写：

- `id`：稳定 ID，使用 kebab-case，例如 `web-research`；必须和父目录 `skills/chat/<skill-id>/` 中的 `<skill-id>` 一致
- 文件路径：必须放在 `skills/chat/<skill-id>/<lang>.json`，`<lang>` 当前支持 `cn` 和 `en`
- `name`：用户看到的名称，必须清晰、聚焦；推荐使用 `{ "cn": "...", "en": "..." }`
- `description`：说明这个技能适合什么任务；推荐使用 `{ "cn": "...", "en": "..." }`
- `launch`：点击技能后进入聊天还是工作区
- `instructions`：模型运行时的任务说明
- `model`：模型偏好、候选模型或是否跟随全局模型
- `tools`：内置工具，例如 `web_search`，其中 `name/description` 支持中英文
- `toolServers`：由 Tool Server 承载的工具依赖，例如 `fetch`、`brave-search`，其中 `name` 支持中英文
- `permissions`：网络、文件、钱包等权限声明
- `release`：发布状态和审核状态

生成发布清单：

```bash
npm run check
```

该命令会生成：

- `index.json`：轻量技能索引
- `packages.json`：Chat 实际加载的技能包列表

这两个文件需要和技能源码一起提交。

## 3. 作者怎么发布工具

复制模板：

```bash
cp templates/tool-server.json tools/servers/<tool-id>.json
```

编辑 Tool Server 包时重点填写：

- `id`：稳定 ID，使用 kebab-case，例如 `brave-search`
- `name`：用户看到的名称，必须清晰、聚焦；推荐使用 `{ "cn": "...", "en": "..." }`
- `description`：说明这个工具适合提供什么模型可调用能力；推荐使用 `{ "cn": "...", "en": "..." }`
- `repo`：源码或官方说明地址
- `command`：启动命令，例如 `npx`、`uvx`
- `baseArgs`：启动参数，不包含用户密钥
- `configurable`：是否需要用户配置
- `configSchema`：需要用户填写的配置项，配置项的 `description/helpLabel/itemLabel/addButtonText` 支持中英文
- `argsMapping`：配置项如何映射到参数或环境变量
- `release`：发布状态和审核状态

生成发布清单：

```bash
npm run check
```

该命令会生成：

- `tools/index.json`：轻量工具索引
- `tools/packages.json`：Chat 实际加载的 Tool Server 包列表

这两个文件需要和工具源码包一起提交。

## 4. 维护者怎么审核

审核重点：

- 技能名称是否清晰，避免“高效助手”这类泛化名称
- 技能是否解决明确任务，而不是包装一个泛化人格
- instructions 是否具体、可执行
- 是否包含密钥、私有 URL、本地路径或敏感信息
- 模型需求是否合理
- 工具依赖是否显式声明
- 必需依赖是否标记为 `required: true`
- 可选依赖是否标记为 `required: false`
- 权限声明是否和任务一致
- 引用开源内容时是否满足 license 和 attribution 要求

工具额外审核：

- 启动命令是否来自可信包或可信仓库
- 是否要求用户密钥，且密钥只通过配置项注入
- 是否包含本地绝对路径、私有地址或硬编码 token
- 权限边界是否清晰，例如文件、网络、钱包
- 是否能被技能通过稳定工具 ID 依赖

## 5. 怎么上线

PR 合并到 `main` 后，技能或工具即上线。

Chat 当前技能包远程加载地址：

```txt
https://raw.githubusercontent.com/yeying-community/marketplace/main/packages.json
```

Chat 当前工具包远程加载地址：

```txt
https://raw.githubusercontent.com/yeying-community/marketplace/main/tools/packages.json
```

上线不要求 Chat 发版，前提是：

- 技能只使用当前 Chat 已支持的字段和能力
- `packages.json` 已更新并提交
- 技能依赖的模型或工具可以在用户环境中配置

如果技能依赖 Chat 新能力，需要先升级 Chat，再发布技能。

Tool Server 源码包如果通过 `npx -y @yeying-community/<name>` 启动，还需要发布 npm 包。当前仓库提供 GitHub Actions：

```txt
.github/workflows/publish-tool-packages.yml
```

发布方式和 `web3-bs` 一致，使用仓库 secret：

```txt
npm_token
```

维护者可以在 GitHub Actions 手动触发 `Publish Tool Packages`，选择：

- `all`
- `ifind-data-mcp`
- `qmt-broker-mcp`
- `paper-broker-mcp`

创建 GitHub Release 时也会触发该 workflow。workflow 会先运行 marketplace 校验、子包校验和 `npm pack --dry-run`，再发布 npm 上尚不存在的同版本包；如果某个包的同版本已经发布，会自动跳过。

## 6. 用户怎么配置

技能安装后可能出现三种状态：

| 状态 | 含义 | 用户动作 |
| --- | --- | --- |
| `ready` | 模型和必需工具都可用 | 直接使用 |
| `needs_config` | 有依赖缺失，但可以配置补齐 | 配置模型或工具 |
| `unavailable` | 当前环境无法满足运行条件 | 更换模型或等待能力上线 |

配置项主要有三类：

- 模型：全局模型、技能默认模型、候选模型
- 内置工具：模型服务商提供的能力，例如 `web_search`
- Tool Server：外部工具运行时，例如 `fetch`、`brave-search`

技能包只声明依赖，不应该包含密钥、本地路径或私有服务地址。

## 7. 用户怎么使用

普通聊天：

- 不选择技能
- 使用全局模型
- 不注入技能 instructions
- 不强制绑定工具

聊天类技能：

- 用户点击技能
- Chat 创建技能会话
- 注入技能 instructions
- 应用技能模型配置
- 只注入该技能声明的工具

工作区类技能：

- 用户点击技能
- Chat 进入对应工作区
- 例如图片创作进入 SD 页面

技能入口应该服务于任务，不应该要求用户先理解“类型”再选择技能。

## 8. 升级和下架

升级原则：

- 新用户安装使用新版本
- 已安装技能不应被远程更新静默覆盖
- 历史会话不应被远程更新改变行为

下架建议：

```json
{
  "release": {
    "status": "deprecated"
  }
}
```

状态含义：

- `published`：正常发布
- `deprecated`：不推荐新安装，已安装用户可继续使用
- `removed`：不应进入发布清单

## 9. 常见问题

### 市场里的技能是模板还是直接可用？

市场里的技能应该是“可安装的技能包”，不是模板。

但是否能直接运行，取决于用户环境是否满足模型、工具和权限要求。

### 为什么技能不直接包含工具实现？

工具是运行时服务，涉及本地进程、远程服务、密钥和权限。技能只声明依赖，由用户或组织在运行环境中配置。

### OpenAPI 导入和工具是什么关系？

OpenAPI 导入是 HTTP API 描述，更适合作为 Tool Server 的来源之一。产品入口应该优先呈现工具，而不是把 OpenAPI 和工具平级展示给普通用户。
