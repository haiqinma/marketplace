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

### Configuration

The default file is `~/.yeying/skills/project/config.toml`:

```toml
[project]
url = "https://project.example.com"
access_key = "yyak_..."
secret_key = "<secret shown once>"

[tester]
path = "../tester" # optional; relative to the active product project root
```

Configuration-file selection, from highest to lowest priority:

1. `--config /absolute/path/project.toml`
2. `YEYING_PROJECT_CONFIG`
3. `~/.yeying/skills/project/config.toml`

The environment variables `YEYING_PROJECT_URL`, `YEYING_PROJECT_AK`, and `YEYING_PROJECT_SK` override the corresponding TOML fields when present. For stable local Agent use, prefer the protected TOML file or an approved secret manager rather than shell startup files.

Fields:

- `url`: the Project service origin, without an API path suffix. Obtain it from the Project URL opened in the browser or from the deployment operator.
- `access_key`: the Access Key of a Project automation token.
- `secret_key`: the matching Secret Key. It is shown only when the token is created or rotated.

`[tester].path` is an optional path to the shared `tester` test repository. Relative paths resolve from the active product project's root. When unset, use the sibling path `<product-project-parent>/tester`; this applies across all YeYing community projects. The Project API client reads only `[project]`; `[tester]` is consumed by the Agent workflow.

`tester` is the community's shared Playwright/Chromium E2E suite. Put cross-product user workflows and all E2E cases there, not in a product repository. Product-internal unit tests may remain in each product's native test suite.

#### Obtaining Project AK/SK

1. Sign in to Project with the user whose permissions the Agent should use.
2. Open the avatar menu, choose **Settings → Access Tokens**, or navigate to `/manage/setting/automation-token`.
3. Select **Create Token**, give it a recognizable name, and bind at least one project in which the user is already a member.
4. Enable the **File Cabinet** scope only when the Skill must call file-cabinet commands. Task discussion attachments and execution archives use the selected project's task capability and do not require that extra scope.
5. Choose the offered 7-, 30-, or 90-day lifetime, create the token, and immediately store both Access Key and Secret Key. The Secret Key cannot be recovered after closing the dialog; rotate the token if it is lost.

The token acts as its owner within the selected projects. It does not bypass project membership, task visibility, user state, or file-sharing permissions. Use separate tokens when different automation jobs require different project or scope boundaries.

Protect the local file:

```bash
mkdir -p ~/.yeying/skills/project
chmod 700 ~/.yeying/skills/project
chmod 600 ~/.yeying/skills/project/config.toml
```

Verify read access before any write operation:

```bash
python3 scripts/project_api.py projects
```

Task-local files such as `.project-task-<task-id>.json`, `.project-lifecycle-<task-id>.json`, and `.project-execution-<task-id>.json` are task bindings and lifecycle state, not credential files. They must never contain AK/SK and should remain outside Git.

### Boundaries

AK/SK credentials must never enter the repository, task comments, execution archives, or final responses. Hidden prompts, hidden reasoning, and host data that was not exposed must never be claimed as captured. Implementation should not begin without traceable solution approval, and a task should not be marked complete until verification, pull request metadata, and the execution archive are present. Protocol details are documented in [`references/api.md`](references/api.md).
