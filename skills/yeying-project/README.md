# YeYing Project Collaboration

[简体中文](README_CN.md)

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
