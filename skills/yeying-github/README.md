# YeYing GitHub Delivery

[简体中文](README_CN.md)

### Purpose

`yeying-github` publishes a contributor fork's `main` branch to personal `origin/main`, then reuses or creates a pull request into community `upstream/main`. It supports GitHub API delivery when Git transport is restricted and native Git/gh delivery through repository scripts.

### Configuration

The default configuration file is:

```text
~/.yeying/skills/github/config.toml
```

The configuration has two layers:

1. `[github]` contains defaults used by every repository.
2. `[github.projects.<name>]` is optional and applies only when both configured remotes match the current repository.

There are no separate public and private credential profiles. Repository visibility is metadata, while credentials belong to the default account configuration or a specific project.

### Minimal Default Configuration

This configuration applies to every repository that has no matching project override:

```toml
[github]
mode = "api"                  # api | git
visibility = "auto"           # auto | public | private
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"
fork_token = "<PAT that publishes personal origin/main>"
pull_request_token = "<PAT that reads repositories and manages the upstream PR>"
```

Authentication is inferred automatically:

- A non-empty `fork_token` or `pull_request_token` selects PAT authentication.
- A `[github.github_app]` table selects GitHub App authentication.
- Non-empty PAT fields and a GitHub App table cannot be used together.
- `provider`, shared `token`, `origin_token`, and `upstream_token` are unsupported.

### Project Overrides

Add a project entry only when a repository pair needs settings different from the defaults:

```toml
[github.projects.marketplace]
origin = "liuppx/marketplace"
upstream = "yeying-community/marketplace"
visibility = "public"
```

The project name, such as `marketplace`, is a local identifier. It may contain letters, digits, `_`, and `-`.

The current Git remotes must match both fields, case-insensitively:

```text
origin   -> liuppx/marketplace
upstream -> yeying-community/marketplace
```

If only one side matches, delivery stops with a configuration error. This prevents a typo or copied configuration from silently falling back to global credentials.

The example above inherits global transport, scripts, and credentials, but uses configured public visibility so no dedicated visibility probe is needed.

### Independent Project Credentials

A project can replace the global authentication completely:

```toml
[github.projects.internal_service]
origin = "liuppx/internal-service"
upstream = "example-org/internal-service"
mode = "api"
visibility = "private"
fork_token = "<PAT that writes the private personal fork>"
pull_request_token = "<PAT that reads both repositories and creates the PR>"
```

Authentication is inherited as a unit:

- When a project contains no `fork_token`, `pull_request_token`, or `github_app`, it inherits all global authentication.
- When a project contains any authentication field, it uses only project authentication.
- A project `fork_token` is never combined with a global `pull_request_token`, and the reverse never happens.
- Configure every credential needed by the selected transport in the project table.

This rule makes credential ownership and permission failures predictable.

### Visibility Detection And Token Usage

With the default setting:

```toml
[github]
visibility = "auto"
```

The Skill first selects the matching project configuration or the global default, resolves its PAT or GitHub App credential, and then sends:

```text
GET /repos/<origin-owner>/<origin-repository>
GET /repos/<upstream-owner>/<upstream-repository>
```

Both requests use the selected `pull_request_token`, or the GitHub App user token. The response's `visibility` field, with `private` as a compatibility fallback, determines whether the repositories are public or private. Both repositories must report the same visibility.

This costs two authenticated REST API requests per delivery invocation. A Token is not consumed or shortened by use; the requests count against GitHub's API rate limit. Authenticated user requests commonly have a 5,000-request-per-hour limit, though GitHub account, organization, enterprise, and App policies can change the effective limit.

The Skill no longer probes anonymously. Anonymous GitHub API requests commonly share a 60-request-per-hour IP-based quota, and an exhausted anonymous quota can return HTTP 403. Treating that response as evidence of a private repository caused false private detection in the previous design.

To skip the two dedicated metadata requests, configure visibility explicitly, preferably in the project entry:

```toml
[github.projects.marketplace]
origin = "liuppx/marketplace"
upstream = "yeying-community/marketplace"
visibility = "public"
```

```toml
[github.projects.internal_service]
origin = "liuppx/internal-service"
upstream = "example-org/internal-service"
visibility = "private"
```

Explicit visibility is trusted configuration. API publishing and pull-request operations still make their normal authenticated GitHub API requests, so it does not make API mode token-free.

### Token Responsibilities

| Field | API mode | Git mode | Required permissions |
| --- | --- | --- | --- |
| `fork_token` | Publishes existing local commit/tree/blob objects and updates personal `origin/main` | Unused | Metadata read and Contents read/write on the personal fork |
| `pull_request_token` | Detects visibility when set to `auto`; reads metadata and lists, creates, or updates the upstream PR | Passed temporarily to `pr.sh`/`gh` | Metadata read and Pull requests read/write on upstream; private delivery must read both repositories |

`git commit` is local and never requires a GitHub Token. `fork_token` publishes objects that have already been committed.

When one classic PAT covers both roles, write the same value explicitly in both fields:

```toml
[github]
fork_token = "<the same classic PAT>"
pull_request_token = "<the same classic PAT>"
```

There is deliberately no implicit sharing between the two fields.

### Public Repository PATs

For an ordinary public cross-owner fork, the simplest option is one **Token (classic)** with only:

```text
[x] public_repo
```

Write it into both default fields or both fields of the relevant project override.

For fine-grained PATs:

- `fork_token`: select the personal fork and grant **Contents: Read and write**. Metadata read is included.
- `pull_request_token`: select community upstream and grant **Pull requests: Read and write**. Metadata read is included.

A fine-grained PAT is bound to one resource owner. Administrator or collaborator access to a repository owned by another personal account does not necessarily make that account selectable as the token's resource owner.

### Private Repository PATs

For a private fork and upstream under different resource owners, prefer one controlled **Token (classic)** with:

```text
[x] repo
```

The PAT owner must be able to read both private repositories, update the personal fork, and create a PR into upstream. Complete organization approval, SAML SSO authorization, and IP allow-list requirements where applicable.

When both repositories belong to one resource owner, a fine-grained PAT selecting both repositories with Contents read/write and Pull requests read/write may also work.

Add this scope only when committed changes modify `.github/workflows/`:

```text
[x] workflow
```

Do not request unrelated enterprise, organization, package, hook, user, key, or repository administration scopes.

### GitHub App

Global GitHub App configuration:

```toml
[github.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

Login and store the global App user token:

```bash
python3 scripts/github_app_login.py --project default
```

Project-specific GitHub App configuration:

```toml
[github.projects.internal_service]
origin = "liuppx/internal-service"
upstream = "example-org/internal-service"
visibility = "private"

[github.projects.internal_service.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

Login and store that project's App token:

```bash
python3 scripts/github_app_login.py --project internal_service
```

The App needs **Metadata: Read**, **Contents: Read and write**, and **Pull requests: Read and write**. It must be installed on both repository owners, and the authorizing user must access both repositories. The Skill stores `user_token`, `refresh_token`, and `expires_at` in the selected App table and refreshes expiring user tokens when needed.

### API And Git Modes

API mode uses `fork_token` and `pull_request_token` and is suitable when `git push`, SSH, or `gh` is restricted:

```toml
[github]
mode = "api"
```

Git mode uses `scripts/sync.sh` for fetch/push through SSH or an HTTPS credential helper. `fork_token` may be empty, while `pull_request_token` is used by `scripts/pr.sh` or `gh`:

```toml
[github]
mode = "git"
```

### Precedence

Configuration file:

1. `--config /absolute/path/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

Transport and visibility:

1. `--mode` / `--visibility`
2. `YEYING_GITHUB_MODE` / `YEYING_GITHUB_VISIBILITY`
3. Matching `[github.projects.<name>]`
4. `[github]`
5. Defaults: `api` and `auto`

Authentication:

1. Complete authentication from a matching project that declares any authentication field
2. Complete authentication from `[github]`

### Safety And Operation

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

A configuration containing any token must be mode `0600` or stricter. The Skill does not use ambient `GH_TOKEN`, `GITHUB_TOKEN`, or `UPSTREAM_TOKEN` as configuration, print tokens, force-push, merge PRs, or change repository visibility, branch protection, or collaborators.

Run a dry-run first:

```bash
python3 scripts/github_delivery.py --dry-run \
  --title "chore(scope): accurately describe the delivery"
```
