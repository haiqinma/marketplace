# YeYing GitHub Delivery

[简体中文](README_CN.md)

### Purpose

`yeying-github` implements the YeYing community fork delivery flow: develop on the contributor fork's `main` branch, publish to `origin/main`, and then reuse or create a pull request into the community `upstream/main` branch.

### Transport And Repository Visibility

- `api`: recreate and publish local commits through the GitHub API when `git push`, SSH, or GitHub CLI is restricted.
- `git`: prefer the target repository's existing `scripts/sync.sh` and `scripts/pr.sh`.

Transport and visibility are independent. `mode` selects how commits are published; `visibility` selects how the repository access model is detected or asserted. The recommended setting is `visibility = "auto"`.

Entry point:

```bash
python3 scripts/github_delivery.py \
  --title "feat(scope): accurately describe the complete delivery"
```

### Configuration

The default file is `~/.yeying/skills/github/config.toml`:

```toml
[github]
mode = "api"
visibility = "auto"
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"
origin_token = "<token for the personal fork>"
upstream_token = "<token for the community pull request>"
```

Configuration-file selection, from highest to lowest priority:

1. `--config /absolute/path/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

Transport-mode selection, from highest to lowest priority:

1. `--mode api|git`
2. `YEYING_GITHUB_MODE`
3. `[github].mode`
4. default `api`

Repository-visibility selection, from highest to lowest priority:

1. `--visibility auto|public|private`
2. `YEYING_GITHUB_VISIBILITY`
3. `[github].visibility`
4. default `auto`

Fields:

- `mode`: `api` publishes commits with the GitHub API; `git` uses repository Git/gh scripts.
- `visibility`: `auto` detects both repositories; `public` or `private` asserts the expected state and stops on a mismatch.
- `sync_script`: repository-relative or absolute sync script used in Git mode. Default: `scripts/sync.sh`.
- `pr_script`: repository-relative or absolute pull-request script used in Git mode. Default: `scripts/pr.sh`.
- `origin_token`: reads the fork and updates `origin/main` in API mode.
- `upstream_token`: reads the PR head/base repositories and lists, creates, or updates pull requests on upstream.

Every run performs a read-only GitHub metadata preflight, including `--dry-run`, and prints the resolved `visibility: public` or `visibility: private`. Origin and upstream must have the same visibility. A mixed public/private pair is rejected because this Skill targets a real GitHub fork network.

#### Public/private and API/Git matrix

| Repositories | API mode | Git mode |
| --- | --- | --- |
| Public | `origin_token` writes the fork; `upstream_token` reads both repositories and manages the upstream PR | Git/SSH/HTTPS pushes the fork; public upstream fetch is normally anonymous; `upstream_token` manages the PR |
| Private | `origin_token` reads and writes the private fork; `upstream_token` reads both private repositories and manages the upstream PR | Git/SSH/HTTPS credentials access both private remotes; `upstream_token` also reads both repositories and manages the PR |

Choose `api` when the environment restricts `git push`, SSH, or `gh`. Choose `git` when the repository scripts and Git credentials are already established. Keep `auto` for normal use; select `public` or `private` when a visibility mismatch must be treated as configuration failure.

#### Obtaining GitHub tokens

Open GitHub **Settings → Developer settings → Personal access tokens** and create a fine-grained token or, when a private cross-owner PR cannot be represented by one fine-grained resource owner, an appropriately controlled classic token or GitHub App credential.

- The origin credential is used in API mode. It needs access to the contributor fork, Metadata read permission, and Contents read/write permission.
- The upstream credential is used in both modes. It needs Metadata read access, visibility into both PR repositories, and Pull requests read/write permission on the community repository.
- For a PR between two private repositories owned by different accounts or organizations, a fine-grained token restricted to one resource owner may not see both sides. Use one approved credential that can read both repositories and manage upstream pull requests.
- Private organization repositories may also require SAML SSO authorization, PAT approval, or compliance with an IP allow list. GitHub may return `403`, or `404` to conceal a private repository, when those requirements are not met.
- A classic PAT typically needs `public_repo` for public repositories or `repo` for private repositories. Prefer fine-grained repository selection when it can cover the complete workflow.
- Create the narrowest practical repository selection and expiry. Revoke or rotate the credential when the delivery environment changes.

GitHub shows a newly created PAT value only at creation time. Store it directly in the protected local file; do not paste it into shell history, issue text, PR bodies, or repository files.

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

The Skill deliberately ignores ambient `GH_TOKEN`, `GITHUB_TOKEN`, and `UPSTREAM_TOKEN` as configuration. Git mode may inject the configured `upstream_token` as `GH_TOKEN` only inside a child `gh`/`pr.sh` process for compatibility.

In Git mode, TOML tokens do not authenticate `git fetch` or `git push`. Configure the remote URLs with an authorized SSH key or an HTTPS credential helper. Public upstream fetch normally needs no credential; private origin and upstream remotes both require Git access. `origin_token` is not injected into `sync.sh`.

Validate configuration and remote state without writing:

```bash
python3 scripts/github_delivery.py --mode api --visibility auto --dry-run \
  --title "docs(scope): describe the complete delivery"
```

### Safety

The Skill does not force-push, merge pull requests, change branch protection, add collaborators, or change repository visibility. Never print token values. Additional details are in [`references/configuration.md`](references/configuration.md).
