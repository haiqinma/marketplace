# 夜莺项目协作 / YeYing Project Collaboration

## 中文

### 用途

`yeying-project` 通过 AK/SK 签名 API 管理夜莺产品研发任务的完整生命周期，包括任务接收、分析、方案审批、实现、验证、GitHub 交付和审计归档。

### 核心能力

- 创建、读取和更新 Project 任务及评论。
- 将本地工作区绑定到明确的 Project 任务。
- 使用带任务 ID 后缀的本地文件隔离并行任务。
- 记录分析、审批、文档、验证、提交和 PR 结果。
- 归档 Codex、Claude 或其他 Agent 可公开获得的执行历史和真实模型信息。
- 管理 Project 文件柜并发布经过审阅的本地文档。

### 配置与边界

默认配置文件是 `~/.yeying/skills/project/config.toml`，应设置为 `0600`。AK/SK 不得进入仓库、任务评论、执行归档或最终回复。隐藏提示、隐藏推理和宿主未暴露的工具输出不得声称已被捕获。未经可追溯的方案批准，不应开始实现；验证、PR 和执行归档不完整时，不应把任务标记为完成。

## English

### Purpose

`yeying-project` manages the full YeYing product development lifecycle through AK/SK-signed APIs, including intake, analysis, solution approval, implementation, verification, GitHub delivery, and audit archival.

### Core Capabilities

- Create, read, and update Project tasks and comments.
- Bind a local workspace to an explicit Project task.
- Isolate parallel tasks with task-ID-suffixed local files.
- Record analysis, approval, documentation, verification, commits, and pull request results.
- Archive the execution history and real model information exposed by Codex, Claude, or another Agent.
- Manage the Project file cabinet and publish reviewed local documents.

### Configuration and Boundaries

The default configuration file is `~/.yeying/skills/project/config.toml` and should use mode `0600`. AK/SK credentials must never enter the repository, task comments, execution archives, or final responses. Hidden prompts, hidden reasoning, and host data that was not exposed must never be claimed as captured. Implementation should not begin without traceable solution approval, and a task should not be marked complete until verification, pull request metadata, and the execution archive are present.
