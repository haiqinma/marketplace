# Codex 执行类技能

本文说明 `skills/codex/` 下的 Codex 技能定位、目录结构和维护规则。

## 定位

`skills/codex/` 保存面向 Codex 的执行类技能，用于沉淀社区项目中的重复工程方法，例如：

- Warehouse、Router、Knowledge、Project 等单产品 Tool 化、MCP 接入和 Agent 化；
- Project 任务协作和文件柜同步；
- 后续可复用的部署、发布、审计或迁移流程。

这类技能不是 Chat Marketplace 的用户技能包，不使用 `skills/chat/<skill-id>/<lang>.json` 格式，也不会被当前 `scripts/build.mjs` 写入 `packages.json`。

## 目录结构

每个 Codex 技能使用独立目录：

```text
skills/codex/<skill-id>/
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
  assets/
```

只有 `SKILL.md` 是必需文件。`references/`、`scripts/` 和 `assets/` 只在确有复用价值时增加。

## 命名模板

Codex 执行类技能统一使用：

```text
community-<scope>-skill
```

- `community`：固定前缀，表示这是社区维护的 Codex 执行类技能，区别于系统技能、个人本地技能和 Chat 用户技能包。
- `<scope>`：技能归属范围。产品能力必须使用产品 slug；横向流程只有在不能归属到单个产品时才使用领域 slug。
- `skill`：固定后缀，表示该目录是 Codex 执行类技能。具体能力边界写入 `description`、`SKILL.md` 正文和必要的 `references/`，不继续拆到名称中。

命名约束：

- 全部小写，使用 kebab-case，只包含小写字母、数字和连字符。
- 目录名、`SKILL.md` frontmatter 的 `name`、文档引用和 `$skill-name` 调用名必须一致。
- 名称控制在 64 个字符以内；不使用阶段、版本、人名或临时项目代号。
- 产品 slug 采用社区产品的稳定英文名，例如 `chat`、`knowledge`、`warehouse`、`project`、`node`、`router`、`agent`、`marketplace`、`wallet`。
- 不使用 `product`、`general`、`common`、`all` 这类泛 scope 承载多个产品的执行规则；通用概念沉淀到文档或引用模板，产品落地拆到对应产品 skill。
- 横向流程 scope 只用于明确的非产品工作流，例如 `docs`、`release`、`ops`、`security`、`identity`，不重复写成 `community-community-skill`。
- 初期按一个产品一个 skill 管理；同一产品内的 Tool、MCP、Agent、部署、运维等能力优先放在该产品 skill 的正文或 `references/` 中，避免过早拆成多个 skill。

示例：

| 场景 | 推荐名称 |
| --- | --- |
| Project 任务协作和文件柜同步 | `community-project-skill` |
| Warehouse 对模型开放资料访问工具 | `community-warehouse-skill` |
| Router 模型渠道、额度和计量治理 | `community-router-skill` |
| Knowledge 资料加工、记忆和检索接入 | `community-knowledge-skill` |
| Node 应用、Tool、Skill、Agent 发布目录 | `community-node-skill` |
| 社区文档同步到共享系统 | `community-docs-skill` |

历史短名、能力型名称或泛 scope 名称（例如 `project-collaboration`、`community-project-collaboration`、`community-product-tool-agent`、`community-product-skill`）不作为新技能主名称继续扩散。已有外部引用如需兼容，应在迁移期通过文档说明或调用方配置处理，不再新增同义目录。

## 当前技能

| Skill | 用途 |
| --- | --- |
| `community-project-skill` | 通过 Project 标准 API 读取任务、更新评论、同步文件柜文档 |
| `community-warehouse-skill` | 按统一契约推进 Warehouse Tool 化、MCP 接入和 Agent 编排 |

## 维护规则

- 技能说明必须聚焦实际任务，不写泛化人格设定。
- 不在技能中硬编码本地绝对路径、AK/SK、Token、Cookie、私有地址或生产密钥。
- 涉及外部写操作时，技能只定义边界和检查项，不替代用户授权。
- 涉及社区产品边界时，必须区分当前已实现能力、规划能力和历史兼容命名。
- 技能引用的脚本、模板或参考文档必须随目录一起提交，并能独立说明用途。

## 校验

新增或修改 Codex 技能后，至少执行：

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/codex/<skill-id>
```

Chat 技能和 Tool Server 的发布清单仍使用：

```bash
npm run check
```

`npm run check` 当前不会处理 `skills/codex/`。
