---
name: yeying-project
description: Manage YeYing Project development tasks across intake, analysis, solution approval, implementation, verification, delivery, and audit with AK/SK-signed APIs. Create and update tasks, bind workspaces, associate Codex/Claude/other Agent execution archives, record repository commits and GitHub PR results, and manage the Project file cabinet. Use when a YeYing product task needs a traceable end-to-end delivery workflow; hidden prompts or hidden reasoning are never claimed as captured.
---

# Community Project Collaboration

Use the bundled client to treat Project as the source of truth for task context and lifecycle decisions, the local repository as the code source, and GitHub as the PR delivery source. Never place AK/SK credentials in a repository, command output, task comment, archive, or final response.

The standard lifecycle is documented in [references/lifecycle.md](references/lifecycle.md). Do not start implementation before the task has a recorded analysis, a feasible solution, acceptance criteria, and explicit approval. Before verification, record the documentation closeout for local `docs` and `books/yeying`: updated, checked with no change needed (with reason), and any cross-project impact. Do not mark work complete before verification, PR metadata, and the execution archive are associated with the same task.

For work performed by Codex, Claude, or another Agent on a specific task, use the independent execution archive workflow in [references/execution-archive.md](references/execution-archive.md). It records the available execution history, publishes the archive as task attachments, and writes one idempotent task reference. This workflow belongs to Project and does not require or call `yeying-warehouse`.

## Client

Run:

```bash
python3 scripts/project_api.py <command> [options]
```

The script resolves configuration in this order:

1. command-line `--config`
2. `YEYING_PROJECT_CONFIG`
3. `~/.yeying/skills/project/config.toml`

The configuration file is TOML:

```toml
[project]
url = "http://127.0.0.1:8080"
access_key = "your-project-access-key"
secret_key = "your-project-secret-key"

[tester]
path = "../tester" # optional; relative to the active project root
```

Use a custom file with:

```bash
python3 scripts/project_api.py --config /path/to/project.toml projects
```

Create the default file at `~/.yeying/skills/project/config.toml`, or point `YEYING_PROJECT_CONFIG` to another local TOML file. Environment variables `YEYING_PROJECT_URL`, `YEYING_PROJECT_AK`, and `YEYING_PROJECT_SK` take precedence over the corresponding TOML fields. Keep this file outside Git and restrict its permissions, for example `chmod 600 ~/.yeying/skills/project/config.toml`.

For new E2E or user-workflow test cases across all YeYing community projects, use the shared Playwright `tester` repository. Its path can be set with `[tester].path` in the selected config; relative paths resolve from the active product project's root. If unset, use the sibling path `<product-project-parent>/tester`. The Project API client only reads `[project]`; `[tester]` is consumed by this workflow. Never add E2E cases to a community project repository. Product-internal unit tests may remain in the product's native test suite.

Legacy JSON files are not part of the shared skill configuration contract.

The Project API configuration and task binding are separate: `.project-task-<task-id>.json` contains only `project_id` and `task_id`, never AK/SK. Each task uses isolated local files: `.project-task-<task-id>.json`, `.project-lifecycle-<task-id>.json`, `.project-execution-<task-id>.json`, and `.project-execution-<task-id>/`. The capture scripts resolve task binding from explicit arguments, `YEYING_PROJECT_ID`/`YEYING_PROJECT_TASK_ID`, or the nearest task-specific marker. If multiple markers exist, callers must select a task explicitly.

Available commands:

### Task collaboration

```bash
python3 scripts/project_api.py projects
python3 scripts/project_api.py tasks --project-id 8
python3 scripts/project_api.py task-create --project-id 8 --name "实现某功能" --content-file /tmp/request.md
python3 scripts/project_api.py task --task-id 123
python3 scripts/project_api.py comment --task-id 123 --model "<model-id>" --content "已完成实现和验证。"
python3 scripts/project_api.py comment --task-id 123 --model "<model-id>" --content-file /tmp/project-update.md
python3 scripts/project_api.py comment --task-id 123 --model "<model-id>" --update-id 456 --content-file /tmp/project-update.md
python3 scripts/project_api.py update --task-id 123 --name "新标题"
python3 scripts/project_api.py update --task-id 123 --content-file /tmp/task.md
python3 scripts/project_api.py status --task-id 123 --flow-item-id 9
python3 scripts/project_api.py status --task-id 123 --completed
python3 scripts/project_api.py file-info --file-id 456
python3 scripts/project_api.py download --file-id 456 --output /tmp/document.pdf

# lifecycle state and gates
python3 scripts/project_lifecycle.py bind --project-id 8 --task-id 123 --workdir /path/to/repository --source-tool codex --model "<model-id>"
python3 scripts/project_lifecycle.py record --state /path/to/repository/.project-lifecycle-123.json --kind analysis --file /tmp/analysis.json --publish
python3 scripts/project_lifecycle.py record --state /path/to/repository/.project-lifecycle-123.json --kind documentation --file /tmp/documentation.json --publish
python3 scripts/project_lifecycle.py approve --state /path/to/repository/.project-lifecycle-123.json --by "负责人" --reference "Project 评论或会议记录引用"
python3 scripts/project_lifecycle.py archive-link --state /path/to/repository/.project-lifecycle-123.json --manifest /path/to/repository/.project-execution-123/manifest.json --publish
python3 scripts/project_lifecycle.py advance --state /path/to/repository/.project-lifecycle-123.json --to implementation

# Task execution archive
python3 scripts/project_execution_archive.py start --project-id 8 --task-id 123 --source-tool codex --model "<model-id>" --state /path/to/repository/.project-execution-123.json --output-dir /path/to/repository/.project-execution-123 --lifecycle-file /path/to/repository/.project-lifecycle-123.json
python3 scripts/project_execution_archive.py append --state /path/to/repository/.project-execution-123.json --role user --content "用户请求"
python3 scripts/project_execution_archive.py finalize --state /path/to/repository/.project-execution-123.json --incomplete --missing "平台隐藏上下文"
python3 scripts/project_execution_archive.py publish --state /path/to/repository/.project-execution-123.json

# 客户端 JSONL 自动采集桥接器
cat events.jsonl | python3 scripts/project_execution_capture.py \
  --project-id 8 --task-id 123 --source-tool claude --model "<model-id>" \
  --state /path/to/repository/.project-execution-123.json \
  --output-dir /path/to/repository/.project-execution-123 \
  --lifecycle-file /path/to/repository/.project-lifecycle-123.json \
  --incomplete --missing "客户端未提供隐藏上下文" --publish
```

### File cabinet management

```bash
# List files in a directory (pid=0 for root)
python3 scripts/project_api.py file-lists --pid 0

# Get file metadata, optionally with download URL or extracted text
python3 scripts/project_api.py file-one --id 18
python3 scripts/project_api.py file-one --id 18 --with-url yes
python3 scripts/project_api.py file-one --id 18 --with-text yes

# Create a folder or document (type: folder, document, mind, drawio, word, excel, ppt)
python3 scripts/project_api.py file-add --name "社区产品" --type folder --pid 0
python3 scripts/project_api.py file-add --name "架构文档" --type document --pid 17

# Save Markdown content into an existing document
python3 scripts/project_api.py file-save --id 18 --content "# Title\n\nBody text."
python3 scripts/project_api.py file-save --id 18 --content-file /tmp/doc.md

# Read document content (returns parsed JSON with content field)
python3 scripts/project_api.py file-read --id 18

# Upload a local file to the file cabinet
python3 scripts/project_api.py file-upload --pid 0 --file /tmp/report.pdf
python3 scripts/project_api.py file-upload --pid 17 --file /tmp/spec.md --cover 1

# Search files by name
python3 scripts/project_api.py file-search --key "架构"

# Generate or refresh a share link (guest-access=yes for non-logged-in viewers)
python3 scripts/project_api.py file-link --id 18 --guest-access yes
python3 scripts/project_api.py file-link --id 18 --refresh yes

# Delete files or folders
python3 scripts/project_api.py file-remove --ids 18 19

# Move files or folders to a target folder
python3 scripts/project_api.py file-move --ids 18 --pid 17
```

All successful commands print JSON to stdout. Failures print a concise error to stderr and return a nonzero exit code.

## Task Workflow

1. Resolve or create the task. If the user gives a task ID, call `task`; otherwise list `projects` and `tasks`, or use `task-create` when the request has no existing task.
2. Bind the repository with `project_lifecycle.py bind` or create-and-bind it with `project_lifecycle.py create`; keep `.project-task-*.json`, `.project-lifecycle-*.json`, `.project-execution-*.json`, and `.project-execution-*/` out of Git.
3. Read the task title, description, content, members, tags, and recent discussion. Record the analysis and feasible solution, including scope, non-goals, risks, acceptance criteria, and test plan.
4. Obtain explicit solution approval and advance the lifecycle gate before changing code. A verbal or hidden approval that has no traceable reference does not satisfy the gate.
5. Inspect the local repository and perform the requested work using its own instructions and quality gates. Keep structured implementation records in the lifecycle state.
6. Before verification, inspect and update affected local `docs` and `books/yeying` documents. Record the paths, update status, no-change reason when applicable, and cross-project impact as a `documentation` record. PlantUML is optional and should be used only when it makes a complex flow easier to read.
7. When a task requires E2E or user-workflow tests, follow [references/testing.md](references/testing.md) and add them to the shared `tester` repository; do not add E2E cases to the product repo. Keep implementation-internal unit tests in the product's native suite when appropriate. Run verification and record `passed=true` only when the acceptance criteria, test results, and documentation closeout are covered. Use `github-api-push` for GitHub push/PR operations, then record the exact repository, branch, commit SHA, PR URL/number, CI and review state in a `pull_request` record.
8. Capture and publish the available AI execution history with the same task and `executionId`; associate the lifecycle snapshot with `project_execution_archive.py finalize`.
9. Advance to `completed` only after the PR, verification and audit archive are all present. Post a concise durable result comment; do not post routine tool narration.
10. Keep the user's chat response aligned with what was written back to Project.

Task comments, lifecycle record publication, and execution archive publication automatically call Project's task-dialog endpoint. If the task has no `dialog_id`, Project creates the chat and returns its reusable ID. The caller still needs project membership and task visibility.

## Task Execution Archive

When an AI client or Agent is carrying out a concrete Project task, preserve the complete history available to the caller: user messages, assistant messages, tool calls, tool results, attachment references, decisions, and the final result. Start an `executionId`, append records as they become available, finalize the three archive files, then publish them to the task. The archive must be marked incomplete when the host cannot expose hidden context or full tool output. Use the same `executionId` for retries so publication can verify and reuse existing task attachments.

Pass the real active model ID supplied by the host through `--model` whenever it is available. Never infer a model from `source_tool`, a client name, or a vendor default. The scripts also accept `YEYING_AGENT_MODEL`, `YEYING_AGENT_MODEL_PROVIDER`, `YEYING_AGENT_CLIENT_VERSION`, `YEYING_AGENT_REASONING_EFFORT`, and `YEYING_AGENT_SOURCE_TOOL`; explicit arguments take precedence. When the host does not expose a model, the archive keeps `model_missing_reason` instead of inventing one. The explicitly supplied model remains `primary`; other distinct models found in public client events are recorded as `participant`. Finalization freezes the model set so retries cannot silently change the identity of an already generated or published archive.

For automatic client integration, use the client-neutral JSONL bridge described in [references/auto-capture.md](references/auto-capture.md). The bridge accepts events from hooks, wrappers, or native event streams; it does not claim access to hidden prompts or internal reasoning and must not upload when the target task is ambiguous.

Claude Code hook payloads can be translated with `scripts/project_claude_hook.py`; Codex or other Agent JSONL can be translated with `scripts/project_codex_events.py`. These adapters do not install hooks or alter client configuration automatically. The host must explicitly register them and provide a reliable Project task binding.

The capture bridge can discover `project_id` and `task_id` from explicit arguments, `YEYING_PROJECT_ID`/`YEYING_PROJECT_TASK_ID`, or the nearest `.project-task-<task-id>.json`. It fails closed when the binding is incomplete or multiple task markers exist without an explicit task selection.

For one-event-at-a-time Claude hooks, use `scripts/project_execution_event.py` as described in [references/claude-hooks.md](references/claude-hooks.md). It persists each event before the next hook starts and only finalizes on an explicit stop/session-end hook.

When a solution needs human confirmation, publish the solution and end the current generation turn. Do not poll, heartbeat, or schedule model calls while waiting. On a later user turn, re-read the task discussion and either record approval, revise the solution, or record rejection. This skill does not determine the host's subscription or token billing rules.

## File Cabinet Workflow

The file cabinet is a per-user document store with optional sharing. Files are organized in a folder tree; root is `pid=0`.

1. Use `file-lists --pid 0` to see the top-level folders and files.
2. Use `file-search --key "xxx"` to find a file by name across owned and shared files.
3. Use `file-add --name "xxx" --type folder` to create a folder, or `--type document` for a Markdown document.
4. Use `file-save --id N --content-file path/to/doc.md` to write Markdown content into a document.
5. Use `file-read --id N` to retrieve the rendered content of a document.
6. Use `file-upload --pid N --file path/to/local/file` to upload binary or text files.
7. Use `file-link --id N --guest-access yes` to generate a public share link for non-logged-in viewers.
8. Use `file-one --id N --with-text yes` when you need the extracted text of a document for AI reading.

File cabinet commands require an AK/SK token created with the Project `file_cabinet` permission scope. With that scope, the token can access files owned by the token user, files created by the token user, and files shared to the token user. Files owned by other users are inaccessible unless explicitly shared.

## Local Document Publishing

Use this skill when a user asks to publish local repository code or `docs/` documents to Project for members who cannot access the repository.

The first phase is deliberately one-way: the Git repository is the editing source and Project File Cabinet is the shared reading/publishing copy. Do not silently overwrite a document that may have been edited in Project.

For YeYing community architecture documents, treat `/Users/liuxin2/Workspace/opensource/books/yeying` as the publication source. Use the source code, README files, routes, configuration, and `docs/` under the related `/Users/liuxin2/Workspace/opensource/*` projects as evidence when updating those documents. Publish only the reviewed documents from `books/yeying`; do not directly expose project source code or internal docs through the public file cabinet.

Workflow:

1. Restrict the publication set to the requested reviewed document paths, normally `books/yeying` for community documents and explicitly named Markdown or attachment files.
2. Scan content for credentials and reject files containing AK, SK, APP_KEY, private keys, passwords, cookies, or production tokens.
3. Resolve the target folder with `file-lists`; use `file-search` or a stored file ID before creating anything.
4. In plan/check mode, report files to create, update, skip, or flag as conflicts without writing.
5. In apply mode, create missing folders/documents with `file-add`, then write Markdown with `file-save` or upload binary attachments with `file-upload`.
6. Read every written document back with `file-read` and verify its title and content digest before reporting success.
7. Record source path, source SHA-256, target file ID, target folder ID, commit (when available), and sync time in a local state file that contains no credentials.

Conflict rule: if the target content differs from the last published source baseline and the local source also changed, stop and report the conflict. Do not overwrite it without explicit user confirmation. Delete and move operations are never part of an automatic publish.

For guest links, default to `guest_access=no`. Enable guest access only after the user explicitly confirms that the document is suitable for public reading. Sensitive architecture, authentication, token, wallet, and security documents should use Project-user sharing instead.

The current client provides the primitive file cabinet commands; a future repository sync wrapper may add `check`, `plan`, and `apply` modes, but it must reuse the same signed API client and permission boundaries.

The bundled first-phase wrapper is available as:

```bash
python3 scripts/project_docs_sync.py check --config docs-sync.json
python3 scripts/project_docs_sync.py plan --config docs-sync.json --project-config /path/to/project.toml
python3 scripts/project_docs_sync.py apply --config docs-sync.json --project-config /path/to/project.toml
```

`check` does not require Project credentials. `plan` and `apply` require an AK/SK token created with the Project `file_cabinet` permission scope. The wrapper writes a local state file beside the configuration (or the path passed with `--state`); keep that state out of source control when it contains environment-specific file IDs.

See [references/document-sync.md](references/document-sync.md) for the JSON configuration format and the recommended execution sequence.

## Comment Rules

- Write comments in the user's language unless the task establishes another language.
- Keep comments factual and compact. Prefer a short heading followed by flat bullets.
- Put the decision, current stage, next step, verification state, and missing items before large raw records. Wrap raw JSON or tool output in `<details>` when the Project Markdown renderer supports it; never remove the redacted source record.
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
- Treat `file-add`, `file-save`, `file-upload`, `file-remove`, `file-move`, and `file-link` as file cabinet write operations. Confirm the intent before deleting or moving files.
- Never bypass denied operations with browser cookies or unrelated user credentials.

Read [references/api.md](references/api.md) when debugging authentication, adding commands, or interpreting response fields.
