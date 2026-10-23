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
2. `[github.projects.<repository>]` is optional and applies when its key matches the repository name parsed from the current `upstream` Git remote.

There are no separate public and private credential profiles and no `visibility` setting. Credentials belong to the default account configuration or a specific project; actual GitHub operations determine whether those credentials have the required access.

### Minimal Default Configuration

This configuration applies to every repository that has no matching project override:

```toml
[github]
mode = "api"                  # api | git
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

Add a project entry only when an upstream repository needs settings different from the defaults:

```toml
[github.projects.marketplace]
mode = "git"
```

The project key must equal the upstream repository name, case-insensitively. It may contain letters, digits, `_`, and `-`.

For these remotes:

```text
origin   -> liuppx/marketplace
upstream -> yeying-community/marketplace
```

the Skill derives `marketplace` from the actual upstream remote and selects `[github.projects.marketplace]`. The origin owner and repository are always read from the actual `origin` remote and are never duplicated in the configuration.

The example above overrides transport and inherits global scripts and credentials. An empty project table has no practical effect and should be omitted.

Different upstream owners with the same repository name select the same project key. If they need different credentials, keep separate config files and choose one with `--config` or `YEYING_GITHUB_CONFIG`.

### Independent Project Credentials

A project can replace the global authentication completely:

```toml
[github.projects.internal-service]
mode = "api"
fork_token = "<PAT that writes the private personal fork>"
pull_request_token = "<PAT that reads both repositories and creates the PR>"
```

Authentication is inherited as a unit:

- When a project contains no `fork_token`, `pull_request_token`, or `github_app`, it inherits all global authentication.
- When a project contains any authentication field, it uses only project authentication.
- A project `fork_token` is never combined with a global `pull_request_token`, and the reverse never happens.
- Configure every credential needed by the selected transport in the project table.

This rule makes credential ownership and permission failures predictable.

### Repository Access And Token Usage

The Skill does not perform a dedicated public/private visibility probe. Visibility does not affect credential selection or the delivery algorithm, so probing it would add configuration and API requests without changing behavior.

Access is checked by the operation that needs it:

- `fork_token` accesses and updates personal `origin/main` in API mode.
- `pull_request_token` reads upstream PR data and creates or updates the pull request.
- A GitHub App user token performs both roles.

Private repositories naturally require credentials that can read the affected repositories. Public repositories may need narrower scopes, but no separate runtime branch is required.

A Token is not consumed or shortened by use. GitHub API operations count against the token's rate-limit quota. Authenticated user requests commonly have a 5,000-request-per-hour limit, though account, organization, enterprise, and App policies can change the effective limit.

### Token Responsibilities

| Field | API mode | Git mode | Required permissions |
| --- | --- | --- | --- |
| `fork_token` | Publishes existing local commit/tree/blob objects and updates personal `origin/main` | Unused | Metadata read and Contents read/write on the personal fork |
| `pull_request_token` | Reads required repository and PR data and lists, creates, or updates the upstream PR | Passed temporarily to `pr.sh`/`gh` | Metadata read and Pull requests read/write on upstream; private delivery must read both repositories |

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

Create the token while signed in as the account that owns the personal fork. In GitHub, open **Settings > Developer settings > Personal access tokens > Tokens (classic) > Generate new token (classic)**, select `repo`, choose an expiration, and authorize the token for the upstream organization through **Configure SSO** when SAML SSO is enabled. An organization may also require an administrator to approve the token before private repositories become accessible.

Keep public defaults narrowly scoped and place the private credential in a project override. For example, when the remotes are `liuppx/billing` and `yeying-community/billing`:

```toml
[github.projects.billing]
fork_token = "<liuppx classic PAT with repo scope>"
pull_request_token = "<the same liuppx classic PAT>"
```

The project key is `billing` because the upstream repository is `yeying-community/billing`. Do not add `origin`, `upstream`, `visibility`, or `provider`. Writing the same PAT twice is intentional: `fork_token` updates the personal fork, while `pull_request_token` reads both private repositories and creates the upstream PR. The implementation never shares one field implicitly with the other.

Two fine-grained PATs split across owners are usually insufficient for a private cross-owner PR. A token that can manage upstream but cannot read the private head fork may list upstream PRs successfully and still fail when comparing or creating `fork-owner:main -> upstream-owner:main`.

When both repositories belong to one resource owner, a fine-grained PAT selecting both repositories with Contents read/write and Pull requests read/write may also work.

Add this scope only when committed changes modify `.github/workflows/`:

```text
[x] workflow
```

Do not request unrelated enterprise, organization, package, hook, user, key, or repository administration scopes.

### Private Fork Access Check

Run this read-only check from the target repository after configuring a private project and before the first delivery:

```bash
python3 /path/to/yeying-github/scripts/github_access_check.py
```

The command reads the actual `origin` and `upstream` remotes, selects the project configuration from the upstream repository name, and verifies:

- `origin` is a real GitHub fork whose parent is the configured upstream remote.
- API mode credentials can write the personal fork.
- The PR credential can read both private repositories.
- GitHub can compare `upstream/main...fork-owner:main` with the PR credential.

A ready result ends with:

```text
fork publish access: verified
pull request repository access: verified
private head comparison: verified (ahead=<n>, behind=<n>)
access check: ready
```

For private repositories, HTTP 404 commonly means the selected credential cannot see that repository, not that the repository is absent. If upstream access succeeds but origin or comparison returns 404, replace the split credential setup with one fork-owner Classic PAT using `repo`, or use a GitHub App installed on both owners.

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
[github.projects.internal-service]

[github.projects.internal-service.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

Login and store that project's App token:

```bash
python3 scripts/github_app_login.py --project internal-service
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

Transport:

1. `--mode`
2. `YEYING_GITHUB_MODE`
3. Matching `[github.projects.<repository>]`
4. `[github]`
5. Default: `api`

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
