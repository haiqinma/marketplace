---
name: community-project-skill
description: Access YeYing community Project's standard APIs with AK/SK-signed access tokens to read projects, tasks, discussions, and files or to update task fields, status, and comments. Also manage the Project file cabinet (list, create, read, save, upload, search, link, move, delete documents). Use when Codex needs to fetch work from the community Project product, inspect or update a Project task, download task files, collaborate around a task ID, report progress, synchronize completed work back to Project, or manage shared community documents through the file cabinet.
---

# Community Project Collaboration

Use the bundled client to treat Project as the source of truth for task context and execution updates, and as the shared hub for community documents. Never place AK/SK credentials in a repository, command output, task comment, or final response.

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

### Task collaboration

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

1. Resolve the task. If the user gives a task ID, call `task`. Otherwise list `projects`, select the relevant project from user context, then call `tasks`.
2. Read the task title, description, content, members, tags, and recent discussion before changing code.
3. Inspect the local repository and perform the requested work using its own instructions and quality gates.
4. For substantial work, post a short progress comment only when it provides durable coordination value. Do not post routine tool narration.
5. After verification, post a result comment containing the outcome, important files or behavior changed, tests run, and any blocker or remaining work.
6. Keep the user's chat response aligned with what was written back to Project.

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
python3 scripts/project_docs_sync.py plan --config docs-sync.json
python3 scripts/project_docs_sync.py apply --config docs-sync.json
```

`check` does not require Project credentials. `plan` and `apply` require an AK/SK token created with the Project `file_cabinet` permission scope. The wrapper writes a local state file beside the configuration (or the path passed with `--state`); keep that state out of source control when it contains environment-specific file IDs.

See [references/document-sync.md](references/document-sync.md) for the JSON configuration format and the recommended execution sequence.

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
- Treat `file-add`, `file-save`, `file-upload`, `file-remove`, `file-move`, and `file-link` as file cabinet write operations. Confirm the intent before deleting or moving files.
- Never bypass denied operations with browser cookies or unrelated user credentials.

Read [references/api.md](references/api.md) when debugging authentication, adding commands, or interpreting response fields.
