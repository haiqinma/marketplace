# 自动会话采集边界与事件协议

`community-project-skill` 不直接读取 Codex、Claude 或其他 Agent 的内部会话数据库。客户端必须通过 hook、事件流或 wrapper 输出可公开给宿主的 JSONL 事件，再交给本 Skill 的采集桥接器。

## 任务绑定

采集器可从显式参数、环境变量或工作区标记发现目标任务，优先级如下：

1. `--project-id` 和 `--task-id`；
2. `YEYING_PROJECT_ID` 和 `YEYING_PROJECT_TASK_ID`；
3. 当前目录或父目录最近的 `.project-task-<task-id>.json`；仅当找到唯一标记时可自动选择。

标记文件格式：

```json
{"project_id": 8, "task_id": 123}
```

缺少任一 ID 时采集器失败关闭，不会上传。标记文件只保存任务绑定，不保存 AK/SK。

同一工作区存在多个 `.project-task-<task-id>.json` 时，必须通过 `--task-id` 或 `YEYING_PROJECT_TASK_ID` 选择任务；采集器不会猜测。任务 123 的执行状态和输出目录应分别使用 `.project-execution-123.json` 与 `.project-execution-123/`。

这不是 Project 配置，而是客户端适配层的统一输入协议。适配器只负责把原生事件转换为以下字段，不能上传 AK/SK、Cookie、私钥或隐藏推理内容。

## 事件格式

每行一个 JSON 对象：

```json
{
  "event_id": "evt-001",
  "type": "tool_result",
  "timestamp": "2026-09-29T10:00:00Z",
  "session_id": "client-session-id",
  "role": "tool",
  "content": {"exit_code": 0, "stdout": "done"},
  "metadata": {
    "tool": "exec_command",
    "source_tool": "codex",
    "model": "gpt-5",
    "model_provider": "openai",
    "client_version": "1.2.3",
    "reasoning_effort": "high"
  }
}
```

`type` 建议使用：`session_start`、`user_message`、`assistant_message`、`tool_call`、`tool_result`、`attachment`、`decision`、`session_end`、`session_error`。`role` 可省略，由桥接器按 `type` 推断。

模型相关字段只能来自宿主公开事件或宿主明确传入的参数/环境变量，不能根据客户端名称猜测。桥接器识别 `model`、`model_id`、`model_name`、`provider`/`model_provider`、`client_version`、`reasoning_effort`、`source_tool` 和 `model_role`。显式 `--model` 是主模型；事件中不同的模型会作为 `participant` 保留。没有模型信息时，归档记录 `model_missing_reason`。

## 桥接器

Claude Hook 逐事件持久化方式见 [Claude Code Hook 接入](./claude-hooks.md)。批量 JSONL 仍使用下面的桥接器。

```bash
cat events.jsonl | python3 scripts/project_execution_capture.py \
  --project-id 8 --task-id 123 --source-tool claude --model claude-sonnet \
  --state /path/to/repository/.project-execution-123.json \
  --output-dir /path/to/repository/.project-execution-123 \
  --lifecycle-file /path/to/repository/.project-lifecycle-123.json \
  --incomplete --missing "客户端未提供隐藏上下文"
```

如果工作区只存在一个任务绑定文件，可以省略两个 ID 参数：

```bash
cat events.jsonl | python3 scripts/project_execution_capture.py \
  --source-tool claude --model "<model-id>" \
  --state .project-execution-123.json --output-dir .project-execution-123 \
  --incomplete --missing "客户端未提供隐藏上下文"
```

命令行未方便传值时，可使用 `YEYING_AGENT_SOURCE_TOOL`、`YEYING_AGENT_MODEL`、`YEYING_AGENT_MODEL_PROVIDER`、`YEYING_AGENT_CLIENT_VERSION` 和 `YEYING_AGENT_REASONING_EFFORT`。命令行参数优先于环境变量。归档 finalize 后模型集合被冻结，新模型必须使用新的 execution，避免已发布附件与本地状态不一致。

采集桥接器会：

1. 创建或恢复本地执行状态；
2. 按 `event_id` 去重，支持进程中断后重放；
3. 递归脱敏后写入状态文件；
4. 在输入结束时生成 Markdown、JSON 和 manifest；
5. 可选使用 `--publish` 上传到目标任务。

## 完整性边界

“完整会话”只表示客户端实际提供的公开事件。系统提示词、隐藏推理、平台内部 tool trace 和未暴露的附件不得猜测或伪造。客户端不能提供这些内容时，必须使用 `--incomplete --missing` 标注原因。

## 适配器职责

- Claude：将 Claude Code hook 的 stdin 转为一行 JSONL：

  ```bash
  python3 scripts/project_claude_hook.py >> /tmp/project-events.jsonl
  ```

- Codex：将 Codex 或其他 Agent 的 JSONL 事件标准化：

  ```bash
  cat codex-events.jsonl | python3 scripts/project_codex_events.py >> /tmp/project-events.jsonl
  ```

- 其他 Agent：实现同一 JSONL 协议即可接入。

任务 ID、Project 身份和用户授权仍必须由宿主提供；没有可靠任务绑定时，桥接器不得自动上传。
