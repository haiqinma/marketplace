# Agent 执行类技能

本文说明 `skills/<skill-id>/` 下由 `SKILL.md` 声明的 Agent 技能定位、目录结构和维护规则。

## 定位

Agent 执行类技能面向 Codex、Claude 和其他兼容 `SKILL.md` 的客户端，用于沉淀社区项目中的重复工程方法，例如：

- Warehouse、Router、Knowledge、Project 等单产品 Tool 化、MCP 接入和 Agent 化；
- Project 研发任务全生命周期管理、AI 执行归档和文件柜同步；
- 后续可复用的部署、发布、审计或迁移流程。

所有 Skill 共用 `skills/<skill-id>/` 全局命名空间。Agent 格式使用 `SKILL.md`，Chat 格式使用 `<lang>.json`；同一个 Skill 可以同时支持两种格式。只有存在 `cn.json` 或 `en.json` 的 Skill 才会被 `scripts/build.mjs` 写入 Chat 的 `packages.json`。

## 目录结构

每个 Skill 使用独立的一级目录；Agent 入口和支持资源如下：

```text
skills/<skill-id>/
  README.md
  README_CN.md
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
  assets/
```

`README.md`、`README_CN.md` 和 `SKILL.md` 是必需文件。`README.md` 面向英文开发者，`README_CN.md` 面向中文开发者，两份文档应描述一致的用途、能力、配置和边界，并在顶部互相链接。配置章节必须说明配置文件、解析优先级、字段、默认值、运行依赖和凭证获取入口；没有独立配置文件时也必须明确说明。`SKILL.md` 是 Agent 运行时入口，应保持聚焦，不为了双语展示重复整份运行指令。`references/`、`scripts/` 和 `assets/` 只在确有复用价值时增加。

## 命名模板

夜莺 Agent 执行类技能统一使用：

```text
yeying-<scope>
```

- `yeying`：固定前缀，表示技能属于夜莺产品生态，并在客户端全局 Skill 命名空间中避免与其他社区或组织冲突。
- `<scope>`：技能归属范围。产品能力必须使用产品 slug；横向流程只有在不能归属到单个产品时才使用领域 slug。

目录已经位于 `skills/` 下，且同一目录可以同时提供 Chat 和 Agent 格式，因此名称不再添加没有额外区分度的 `skill` 或 `agent` 后缀。具体能力边界写入 `description`、`SKILL.md` 正文和必要的 `references/`。

命名约束：

- 全部小写，使用 kebab-case，只包含小写字母、数字和连字符。
- 目录名、`SKILL.md` frontmatter 的 `name`、文档引用和 `$skill-name` 调用名必须一致。
- 名称控制在 64 个字符以内；不使用阶段、版本、人名或临时项目代号。
- 产品 slug 采用社区产品的稳定英文名，例如 `chat`、`knowledge`、`warehouse`、`project`、`node`、`router`、`agent`、`marketplace`、`wallet`。
- 不使用 `product`、`general`、`common`、`all` 这类泛 scope 承载多个产品的执行规则；通用概念沉淀到文档或引用模板，产品落地拆到对应产品 skill。
- 横向流程 scope 只用于明确的非产品工作流，例如 `docs`、`release`、`ops`、`security`、`identity`。
- 初期按一个产品一个 skill 管理；同一产品内的 Tool、MCP、Agent、部署、运维等能力优先放在该产品 skill 的正文或 `references/` 中，避免过早拆成多个 skill。

示例：

| 场景 | 推荐名称 |
| --- | --- |
| Project 任务协作和文件柜同步 | `yeying-project` |
| Warehouse 对模型开放资料访问工具 | `yeying-warehouse` |
| 个人 main 发布并向社区 main 提交 PR | `yeying-github` |
| Router 模型渠道、额度和计量治理 | `yeying-router` |
| Knowledge 资料加工、记忆和检索接入 | `yeying-knowledge` |
| Node 应用、Tool、Skill、Agent 发布目录 | `yeying-node` |
| 社区文档同步到共享系统 | `yeying-docs` |

历史短名、能力型名称或泛 scope 名称（例如 `project-collaboration`、`product-tool-agent`、`general-product-skill`）不作为新技能主名称继续扩散。已有外部引用如需兼容，应在迁移期通过文档说明或调用方配置处理，不再新增同义目录。

## 当前技能

| Skill | 用途 |
| --- | --- |
| `yeying-project` | 通过 Project 标准 API 管理研发任务生命周期、文档收口、摘要归档并同步文件柜文档 |
| `yeying-warehouse` | 按统一契约推进 Warehouse Tool 化、MCP 接入和 Agent 编排 |
| `yeying-github` | 在 API 与仓库 Git 脚本之间切换，将个人 `main` 发布到 `origin/main` 并复用或创建面向社区 `upstream/main` 的 PR |

## 维护规则

- 每个 Skill 必须分别提供英文 `README.md` 和中文 `README_CN.md`，两份文档应描述一致的用途、能力、配置和边界。
- 技能说明必须聚焦实际任务，不写泛化人格设定。
- Project 研发任务必须在验证前记录本地 `docs` 和 `books/yeying` 的文档检查结果；复杂流程才使用 PlantUML，简单流程用阶段表即可。
- 执行归档的 Markdown 是摘要优先的阅读入口，原始脱敏事件保留在折叠内容和 `transcript.json`，不得为了可读性删除审计资料。
- 不在技能中硬编码本地绝对路径、AK/SK、Token、Cookie、私有地址或生产密钥。
- 涉及外部写操作时，技能只定义边界和检查项，不替代用户授权。
- 涉及社区产品边界时，必须区分当前已实现能力、规划能力和历史兼容命名。
- 技能引用的脚本、模板或参考文档必须随目录一起提交，并能独立说明用途。

## 校验

新增或修改 Agent 技能后，至少执行：

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/<skill-id>
```

统一目录和 Tool Server 的发布清单校验使用：

```bash
npm run check
```

`npm run check` 会校验每个一级目录都包含英文 `README.md` 和中文 `README_CN.md`，且至少包含 `cn.json`、`en.json` 或 `SKILL.md`；同时验证 Chat `id` 和 Agent `name` 都与目录名一致。Agent-only Skill 不进入 Chat 的 `index.json` 和 `packages.json`。
