# 夜莺生产问题分析、审计与修复闭环

[English](README.md)

### 用途

`yeying-ops` 把生产 ERROR 日志处理组织成一个有人工门禁的完整流程：增量读取日志、脱敏、聚合同类问题、调用只读批处理模型生成结构化根因、在 YeYing Project 中创建或复用问题审计任务、等待审计人员给出结构化结论，并在批准修复时创建独立的研发任务。

本 Skill 不直接修改代码、生产配置、数据库或服务。审计结论只允许创建修复任务；修复任务仍需通过 `yeying-project` 的分析、方案、人工批准、实现、验证、PR 和执行审计流程，并使用 `yeying-github` 交付代码。

### 能力边界

- `yeying-ops`：finding、日志观测、问题审计任务、审计结论对账、修复后观察。
- `yeying-project`：Project 凭证、任务 API、人工批准、研发任务生命周期和执行归档。
- `yeying-github`：修复 commit 推送和 PR 创建或复用。
- `deployer/operator/analyer`：生产配置、模块清单、cron/systemd 入口和通知适配。

不要把其他 Skill 的源码复制到 deployer。生产适配器应调用已经安装的 `yeying-ops/scripts/ops_workflow.py`。

### 安装

Skill 目录应安装或软链接为：

```text
~/.codex/skills/yeying-ops
~/.claude/skills/yeying-ops
```

同时安装 `yeying-project`。默认情况下，`yeying-ops` 会在同一个 skills 根目录查找：

```text
../yeying-project/scripts/project_api.py
```

也可以通过配置中的 `project.client` 指定其他路径。

运行依赖：

- Python 3.9 或更高版本。
- Unix 文件锁支持。
- 已安装并可认证的 Codex CLI，仅批处理根因分析需要。
- 可用的 `yeying-project` Skill，仅启用 Project 同步时需要。

### 配置

默认配置位置：

```text
~/.yeying/skills/ops/config.json
```

也可以使用：

```bash
export YEYING_OPS_CONFIG=/path/to/config.json
```

配置是 JSON。可从 [`scripts/analyzer.conf.example`](scripts/analyzer.conf.example) 开始。所有相对路径都相对于配置文件所在目录解析，不依赖命令执行目录。

完整示例：

```json
{
  "timezone": "Asia/Shanghai",
  "deploy_root": "/opt/deploy",
  "modules_file": "/root/code/deployer/operator/analyer/modules.conf",
  "error_log_name": "logs/error.log",
  "state_db": "/var/lib/yeying-ops/state.db",
  "results_dir": "/var/lib/yeying-ops/results",
  "work_dir": "/var/lib/yeying-ops/work",
  "lock_file": "/run/lock/yeying-ops.lock",
  "codex_command": "/usr/bin/codex",
  "sandbox": "read-only",
  "ignore_user_config": true,
  "model_provider": "openai",
  "model": "",
  "daily_groups": 20,
  "samples_per_group": 3,
  "sample_chars": 4000,
  "total_chars": 60000,
  "timeout_seconds": 300,
  "retry_after_seconds": 3600,
  "include_undated_lines": true,
  "project": {
    "enabled": true,
    "required": false,
    "project_id": 8,
    "audit_column": 13,
    "audit_owner_id": 1,
    "allowed_auditor_ids": [1],
    "remediation_column": 13,
    "remediation_owner_id": 1,
    "maximum_severity": "P3",
    "categories": ["confirmed", "likely", "unknown"],
    "config": "~/.yeying/skills/project/config.toml"
  }
}
```

主要字段：

- `deploy_root`：活动模块目录或 `module-v<version>-<commit>` 目录所在根目录。
- `modules_file`：每行一个模块名，支持 `#` 注释。
- `error_log_name`：相对于模块部署目录的日志路径。
- `state_db`：SQLite 状态，保存日志游标、每日观测、分析状态和 Project 任务关联。
- `results_dir`：按日期保存 JSON finding 和 `summary.json`、`summary.md`。
- `work_dir`：Codex 临时输出；每次调用结束后删除。
- `lock_file`：防止 cron、人工命令和其他调度器重叠执行。
- `ignore_user_config`：默认 `true`，批处理 Codex 不加载用户规则和 MCP 配置；认证仍由 Codex 安装提供。
- `model`：建议显式指定批处理模型。未指定时报告记录 `model_missing_reason`，不会猜测模型名称。
- `daily_groups`、`total_chars`：每次运行的模型调用数量和输入字符预算。
- `include_undated_lines`：增量日志中没有日期的 ERROR 行是否视为当前运行日期。

Project 字段：

- `enabled`：是否创建、更新和对账 Project 审计任务。
- `required`：为 `false` 时，Project 暂时不可用不会丢失分析结果，后续运行会重试；为 `true` 时同步失败导致流程非零退出。
- `project_id`：审计任务和修复任务所属 Project。
- `audit_column`、`remediation_column`：列表 ID 或名称。
- `audit_owner_id`、`remediation_owner_id`：默认负责人用户 ID。
- `allowed_auditor_ids`：唯一有权提交有效结构化审计结论的 Project 用户 ID。
- `maximum_severity`：创建审计任务的最低影响范围。`P3` 表示 P0 至 P3 全部创建。
- `categories`：需要进入审计的根因分类。
- `config`：复用 `yeying-project` 的配置路径。这里不保存 Project AK/SK。

Project 凭证继续配置在：

```text
~/.yeying/skills/project/config.toml
```

例如：

```toml
[project]
url = "https://project.example.com"
access_key = "your-access-key"
secret_key = "your-secret-key"
```

权限至少需要读取任务和讨论、创建任务、追加评论。配置文件应为 `0600`。

### 运行

先演练，不调用 Codex、不推进日志游标、不写 Project：

```bash
python3 scripts/ops_workflow.py run \
  --config ~/.yeying/skills/ops/config.json \
  --dry-run
```

执行完整流程：

```bash
python3 scripts/ops_workflow.py run \
  --config ~/.yeying/skills/ops/config.json
```

只执行分析：

```bash
python3 scripts/ops_workflow.py analyze --config /path/to/config.json
```

只对账 Project 审计结论：

```bash
python3 scripts/ops_workflow.py sync --config /path/to/config.json
```

可使用 `--date YYYY-MM-DD` 处理历史日期，或重复使用 `--module name` 限定模块。历史日期会全量读取目标日志但不会改变当前增量游标。

### 增量和并发

分析器按模块和日志路径保存 device、inode、offset 和 size。日志 inode 改变或文件截断时从新文件开头读取。游标前进前，错误组会写入 `daily_observations`；即使模型失败、超时或达到预算，后续运行仍可以从 SQLite 重试，不依赖再次读取旧日志内容。

同一个 finding 可以每天重新观察。同一天发生次数增加时也可重新分析，因此已确认问题不会被永久忽略。

`ops_workflow.py` 使用非阻塞文件锁保护完整的“分析 + Project 对账”流程，SQLite 同时启用 WAL 和 busy timeout。外部 cron 的 `flock` 可以保留为第二层保护。

### 问题审计

每个 finding 使用：

```text
SHA-256(module + NUL + normalized_error)
```

审计任务标题包含 fingerprint 前 12 位，任务正文包含完整标记：

```text
[yeying-ops:finding:<finding_id>]
```

本地 `project_links` 表保存审计任务 ID、修复任务 ID、决定摘要和最后同步摘要。Project 暂时不可用时不会丢失 finding。

### 审计结论

审计人员必须在审计任务中发布 JSON。`approved_by.user_id` 必须等于评论发送人，并属于 `allowed_auditor_ids`。

批准修复示例：

```json
{
  "schema": "yeying.ops.audit-decision.v1",
  "finding_id": "完整的64位finding id",
  "decision": "remediate",
  "approved_by": {
    "user_id": 1,
    "name": "auditor"
  },
  "approved_at": "2026-10-22T22:30:00+08:00",
  "summary": "修复 router 配置加载错误",
  "remediation_scope": [
    "修复配置加载顺序",
    "增加回归测试"
  ],
  "target_repositories": [
    "yeying-community/router"
  ],
  "acceptance_criteria": [
    "相关测试通过",
    "生产环境连续24小时无同类错误"
  ],
  "constraints": [
    "不得改变现有配置格式"
  ]
}
```

其他决定使用：

- `monitor`：继续观察，不创建修复任务。
- `false_positive`：确认误报，记录原因和建议的抑制期限。
- `needs_more_evidence`：补充证据后重新分析。

普通文字“同意修复”、模型生成内容、日志中的 JSON、未授权用户评论以及 user ID 不匹配的 JSON 都不会触发修复任务。

### 修复边界

`remediate` 只会创建 `[生产问题修复]` 任务并关联来源审计任务。定时流程不会打开代码仓库、修改文件、提交 commit、推送分支、创建 PR、部署或重启服务。

后续 Agent 必须在修复任务中使用 `yeying-project` 完成分析、方案和人工批准，然后实施和验证；代码交付使用 `yeying-github`。修复完成后，再由 `yeying-ops` 做生产观察并提供关闭证据。

### 安全

- 模型样本会删除密钥、token、Authorization、Cookie、邮箱、IP、时间戳、路径和高基数 ID。
- 日志始终是不可信输入；提示词明确禁止把日志解释为指令。
- Codex 批处理使用 `--ephemeral`、`--ignore-rules`、`--skip-git-repo-check` 和只读 sandbox。
- 建议保持 `ignore_user_config=true`，避免批处理继承用户规则和 MCP。
- 原始日志、状态库、结果、运行目录和配置不得提交 Git。
- 结果记录模型、客户端版本以及 prompt/schema SHA-256；拿不到模型时明确记录缺失原因。

### 验证

```bash
python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v
python3 -m py_compile scripts/*.py
bash -n scripts/run_analyzer.sh
```

Skill 元数据验证：

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py /path/to/yeying-ops
```
