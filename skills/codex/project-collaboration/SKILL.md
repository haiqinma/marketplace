---
name: project-collaboration
description: Access YeYing Project's standard APIs with AK/SK-signed access tokens to read projects, tasks, discussions, and files or to update task fields, status, and comments. Use when the user asks Codex to fetch work from Project, inspect or update a Project task, download task files, collaborate around a task ID, report progress, or synchronize completed work back to Project.
---

# Project Collaboration

Use the bundled client to treat Project as the source of truth for task context and execution updates. Never place AK/SK credentials in a repository, command output, task comment, or final response.

## Client

Run:

```bash
python3 scripts/project_api.py <command> [options]
```

The script resolves configuration in this order:

1. `YEYING_PROJECT_URL`, `YEYING_PROJECT_AK`, `YEYING_PROJECT_SK`
2. `YEYING_PROJECT_CONFIG`
3. `~/.config/yeying/project.json`

Available commands:

```bash
python3 scripts/project_api.py projects
python3 scripts/project_api.py tasks --project-id 8
python3 scripts/project_api.py task --task-id 123
python3 scripts/project_api.py comment --task-id 123 --content "已完成实现和验证。"
python3 scripts/project_api.py comment --task-id 123 --content-file /tmp/project-update.md
python3 scripts/project_api.py comment --task-id 123 --update-id 456 --content-file /tmp/project-update.md
python3 scripts/project_api.py update --task-id 123 --name "新标题"
python3 scripts/project_api.py update --task-id 123 --content-file /tmp/task.md
python3 scripts/project_api.py status --task-id 123 --flow-item-id 9
python3 scripts/project_api.py status --task-id 123 --completed
python3 scripts/project_api.py file-info --file-id 456
python3 scripts/project_api.py download --file-id 456 --output /tmp/document.pdf
```

All successful commands print JSON to stdout. Failures print a concise error to stderr and return a nonzero exit code.

## Workflow

1. Resolve the task. If the user gives a task ID, call `task`. Otherwise list `projects`, select the relevant project from user context, then call `tasks`.
2. Read the task title, description, content, members, tags, and recent discussion before changing code.
3. Inspect the local repository and perform the requested work using its own instructions and quality gates.
4. For substantial work, post a short progress comment only when it provides durable coordination value. Do not post routine tool narration.
5. After verification, post a result comment containing the outcome, important files or behavior changed, tests run, and any blocker or remaining work.
6. Keep the user's chat response aligned with what was written back to Project.

## Comment Rules

- Write comments in the user's language unless the task establishes another language.
- Keep comments factual and compact. Prefer a short heading followed by flat bullets.
- For multiline comments, use `--content-file` and write real line breaks. The client also normalizes literal `\\n` sequences from agent command invocations.
- Task details use the Project rich-text HTML contract. Pass Markdown through `update --content` or `update --content-file`; the client converts headings, lists, inline code, emphasis, and HTTP(S) links to editor HTML. Use `--content-format html` only when the input is already Project editor HTML.
- Do not expose secrets, local environment variables, private filesystem paths, or unrelated repository state.
- Do not claim success until required verification has actually passed.
- Ask before posting destructive decisions, scope changes, or sensitive information.
- Avoid duplicate updates. Read recent messages from `task` before commenting.

## Write Boundaries

- Treat `comment`, `comment --update-id`, `update`, and `status` as write operations. Confirm the requested intent and inspect the current task before invoking them.
- Use `comment --update-id` only to correct a message sent by the token owner after reading the current task discussion; it uses the standard message update contract.
- Use `update` only for ordinary task fields exposed by the client. It cannot change assignees, visibility, archive state, or move tasks.
- Use `status` for workflow state or completion only. Prefer the `flows` returned by `task` instead of guessing a flow item ID.
- Download files only when they are relevant to the task. Do not print binary content or credentials.
- Never bypass denied operations with browser cookies or unrelated user credentials.

Read [references/api.md](references/api.md) when debugging authentication, adding commands, or interpreting response fields.
