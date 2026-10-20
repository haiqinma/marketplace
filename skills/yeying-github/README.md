# YeYing GitHub Delivery

[简体中文](README_CN.md)

### Purpose

`yeying-github` publishes a contributor fork's `main` branch to `origin/main`, then reuses or creates a pull request into community `upstream/main`. It supports public and private fork networks through either GitHub API transport or existing repository Git/gh scripts.

### Configuration

The default configuration file is:

```text
~/.yeying/skills/github/config.toml
```

Recommended complete configuration:

```toml
[github]
mode = "api"                  # api | git
visibility = "auto"           # auto | public | private
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"

[github.public]
provider = "pat"              # pat | github_app
fork_token = "<PAT that publishes the public personal fork>"
pull_request_token = "<PAT that creates the public upstream PR>"

[github.private]
provider = "pat"              # pat | github_app
fork_token = "<PAT that publishes the private personal fork>"
pull_request_token = "<PAT that reads both private repositories and creates the PR>"
```

A PAT profile accepts only `fork_token` and `pull_request_token`. There is no shared `token`, no support for former field names, and no credential may be placed directly under `[github]`. Unsupported keys fail immediately with the allowed field list instead of being silently ignored.

### Token Responsibilities

| Field | API mode | Git mode | Required permissions |
| --- | --- | --- | --- |
| `fork_token` | Publishes existing local commit/tree/blob objects and updates personal `origin/main` | Unused | Metadata read and Contents read/write on the personal fork |
| `pull_request_token` | Reads repository metadata and lists, creates, or updates the community upstream PR | Passed temporarily to `pr.sh`/`gh` | Metadata read and Pull requests read/write on upstream; private delivery must read both private repositories |

`git commit` is always local and never requires a GitHub token. `fork_token` is not a commit credential; it publishes objects that have already been committed locally.

When one classic PAT covers both roles, place the same value explicitly in both fields:

```toml
[github.public]
provider = "pat"
fork_token = "<the same classic PAT>"
pull_request_token = "<the same classic PAT>"
```

There is deliberately no implicit sharing or fallback. Each field maps to one execution path, so permission failures identify either fork publication or PR management directly.

### API And Git Modes

API mode:

```toml
[github]
mode = "api"
```

- `fork_token` is required to update personal `origin/main`.
- `pull_request_token` is required for repository checks and PR operations.
- Use this where `git push`, SSH, or `gh` is restricted.

Git mode:

```toml
[github]
mode = "git"
```

- `scripts/sync.sh` uses an SSH key or HTTPS credential helper for fetch and push.
- `fork_token` is not used by Git transport and may be empty.
- `pull_request_token` is used by `scripts/pr.sh` or `gh` to create and update the PR.

### Automatic Visibility Detection

Keep the recommended setting:

```toml
[github]
visibility = "auto"
```

The Skill first reads origin and upstream metadata anonymously. If both are anonymously readable and public, it selects `[github.public]`. Otherwise it loads `[github.private].pull_request_token` and verifies both repositories again. If authenticated access still fails, delivery stops instead of confusing a missing repository, insufficient permission, and a private repository.

Explicit `public` or `private` is an assertion, not a way to skip metadata verification. Delivery also stops when origin and upstream have different visibility.

### Public Repository PATs

The simplest setup for an ordinary external contributor is one **Token (classic)** with only `public_repo`, copied explicitly into both fields:

```toml
[github.public]
provider = "pat"
fork_token = "<classic PAT: public_repo>"
pull_request_token = "<classic PAT: public_repo>"
```

For two fine-grained PATs:

```toml
[github.public]
provider = "pat"
fork_token = "<personal owner; select only the personal fork>"
pull_request_token = "<community organization; select only upstream>"
```

- `fork_token`: grant **Contents: Read and write** on the personal fork. Metadata read is included.
- `pull_request_token`: grant **Pull requests: Read and write** on community upstream. Metadata read is included.

A fine-grained PAT is bound to one resource owner. Administrator or collaborator access to a repository owned by another personal account does not make that account selectable as the token's resource owner. A fine-grained upstream PAT works only when GitHub lets the contributor select the community organization and the organization approves the token where required.

### Private Repository PATs

For a private fork and upstream under different resource owners, prefer one **Token (classic)** with the top-level `repo` scope, copied explicitly into both fields:

```toml
[github.private]
provider = "pat"
fork_token = "<classic PAT: repo>"
pull_request_token = "<classic PAT: repo>"
```

The PAT owner must:

1. Read both private repositories.
2. Update the personal fork.
3. Create a PR from the fork into upstream.
4. Complete organization approval and SAML SSO authorization where required.
5. Operate inside organization, enterprise, and repository policies that permit the private fork network.

When both private repositories belong to one resource owner, a fine-grained PAT selecting both repositories with Contents read/write and Pull requests read/write can also be used.

### Token (classic) Checklist

When both repositories are public:

```text
[x] public_repo
```

When either repository is private:

```text
[x] repo
```

Selecting top-level `repo` automatically selects children such as `repo:status`, `repo_deployment`, `public_repo`, `repo:invite`, and `security_events`. That is expected.

Select this only when committed changes actually modify `.github/workflows/`:

```text
[x] workflow
```

Do not select:

```text
[ ] admin:enterprise
[ ] write:network_configurations
[ ] admin:org
[ ] delete_repo
[ ] packages, hooks, user, audit log, codespaces, Copilot, or projects
[ ] GPG key or SSH signing key administration
```

Classic PATs cannot be limited to selected repositories like fine-grained PATs. Use a short expiration, commonly 30 to 90 days, and rotate according to organization policy.

### GitHub App

GitHub App authentication uses user-to-server Device Flow. One App user token covers both fork and PR roles, so PAT fields are not configured:

```toml
[github.private]
provider = "github_app"

[github.private.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

The App needs **Metadata: Read**, **Contents: Read and write**, and **Pull requests: Read and write**, and it must be installed on both the fork and upstream sides. The authorizing user must also access both repositories.

Login command:

```bash
python3 scripts/github_app_login.py --visibility private
```

The Skill stores `user_token`, `refresh_token`, and `expires_at` in the protected configuration file and refreshes the user token when needed. Cross-owner private PRs do not use installation access tokens because each token belongs to one installation and expires after one hour.

### Configuration Precedence

Configuration file:

1. `--config /absolute/path/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

Transport:

1. `--mode api|git`
2. `YEYING_GITHUB_MODE`
3. `[github].mode`
4. default `api`

Visibility:

1. `--visibility auto|public|private`
2. `YEYING_GITHUB_VISIBILITY`
3. `[github].visibility`
4. default `auto`

### Safety And Operation

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

A configuration containing any token must be mode `0600` or stricter. The Skill does not use ambient `GH_TOKEN`, `GITHUB_TOKEN`, or `UPSTREAM_TOKEN` as configuration, print tokens, force-push, merge PRs, or change repository visibility, branch protection, or collaborators.

Run a dry-run first:

```bash
python3 scripts/github_delivery.py --mode api --visibility auto --dry-run \
  --title "chore(scope): accurately describe the delivery"
```

Then run delivery:

```bash
python3 scripts/github_delivery.py \
  --title "chore(scope): accurately describe the delivery"
```

See [`references/configuration.md`](references/configuration.md) for implementation rules.

Official GitHub references:

- [Managing personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [Create a pull request REST endpoint](https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request)
- [GitHub App user authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user)
