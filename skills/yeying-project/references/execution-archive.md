# 任务执行过程归档

`yeying-project` 可以把一次由 Codex、Claude 或其他 Agent 完成的任务执行过程保存到指定 Project 任务，并和研发生命周期、验证、commit、PR 结果关联。这个能力只理解 Project 任务，不要求 Warehouse，也不要求某一种客户端。

## 生命周期

每次执行使用一个稳定的 `executionId`。调用方负责把能够取得的记录传给脚本：

```bash
python3 scripts/project_execution_archive.py start \
  --project-id 8 --task-id 123 --source-tool codex --model gpt-5 \
  --state /path/to/repository/.project-execution-123.json \
  --output-dir /path/to/repository/.project-execution-123 \
  --lifecycle-file /path/to/repository/.project-lifecycle-123.json

python3 scripts/project_execution_archive.py append \
  --state /path/to/repository/.project-execution-123.json --role user --content "用户请求"

python3 scripts/project_execution_archive.py append \
  --state /path/to/repository/.project-execution-123.json --record-file /tmp/tool-result.json

python3 scripts/project_execution_archive.py finalize \
  --state /path/to/repository/.project-execution-123.json --summary-file /tmp/summary.md \
  --result-file /tmp/result.md --incomplete --missing "平台隐藏上下文"

python3 scripts/project_execution_archive.py publish \
  --state /path/to/repository/.project-execution-123.json
```

`append` 支持用户消息、助手消息、工具调用、工具结果、事件和附件引用。结构化记录使用 `--record-file` 传入 JSON；脚本会在写入状态前递归脱敏。

本地执行状态和输出目录必须按任务隔离，使用 `.project-execution-<task-id>.json` 与 `.project-execution-<task-id>/`。不要让多个任务共享同一个状态文件或输出目录。

## Agent 与模型信息

宿主能够提供当前模型时，必须把真实模型 ID 传给 `--model`。不要根据 `--source-tool`、客户端名称或供应商默认值猜测模型。模型不可得时，状态和 manifest 会保留 `model_missing_reason`，默认说明宿主未暴露当前模型。

除了命令行参数，也可以通过以下环境变量提供公开的执行身份信息；显式参数优先：

- `YEYING_AGENT_SOURCE_TOOL`
- `YEYING_AGENT_MODEL`
- `YEYING_AGENT_MODEL_PROVIDER`
- `YEYING_AGENT_CLIENT_VERSION`
- `YEYING_AGENT_REASONING_EFFORT`

显式传入的模型记录为 `primary`。公开事件中出现的其他模型记录为 `participant`，用于保留一次执行中模型路由、子 Agent 或模型切换的事实。`finalize` 之后模型集合被冻结；可以使用同一模型重试 finalize 或 publish，但不能静默追加不同模型，否则必须开始新的 execution。

## 归档文件

`finalize` 生成：

```text
transcript.md
transcript.json
manifest.json
```

`manifest.json` 记录 `projectId`、`taskId`、`executionId`、结构化 `agent` 上下文、兼容字段 `sourceTool`/`model`、起止时间、记录数量、完整性、缺失项、脱敏标记、生命周期阶段和 transcript 文件的 SHA-256。`agent.models` 中每项可包含模型 ID、`primary`/`participant` 角色、提供方、公开的推理强度及信息来源。若提供生命周期快照，还会记录其摘要哈希；快照中的仓库、commit、PR、验证结果和文档收口记录会进入结构化 transcript。Manifest 不记录自己的 SHA-256，因为文件不能包含自身最终内容的哈希。

`transcript.md` 是面向任务成员的阅读入口：先展示状态、完整性、摘要、结果、生命周期、验证和附件索引；每条原始事件放在 `<details>` 折叠块中。`transcript.json` 保留宿主实际提供的全部脱敏结构化记录，供审计和机器处理。摘要不等于删减原始资料，缺失上下文仍必须在首屏列出。

当宿主环境无法提供隐藏上下文、完整工具结果或附件时，必须使用 `--incomplete --missing "..."`，不能把可见记录宣称为平台底层的完整审计日志。

## 发布和幂等

`publish` 通过 Project 任务对话的文件上传接口发布三个文件，因此文件会出现在任务附件中，并在任务对话追加一条带有 `[execution:<executionId>]` 标记的归档说明。归档说明展示执行工具与主模型，并把主模型作为 Project `sendtext.model_name` 发送；模型不可得时不发送伪造值。

上传文件名固定为：

```text
execution-<executionId>-transcript.md
execution-<executionId>-transcript.json
execution-<executionId>-manifest.json
```

重复执行 `publish` 时，脚本先按确定性文件名查找已有任务附件，下载并比较 SHA-256；内容相同则复用，内容不同则失败，避免静默覆盖。归档说明也按 `executionId` 检查，避免重复写入任务对话。

Project AK/SK 只从现有 `project_api.py` 配置读取，不写入归档内容。文件附件和任务讨论仍受 Project 本身的项目成员与任务权限控制。
