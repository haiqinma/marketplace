# YeYing GitHub Delivery

[简体中文](README_CN.md)

### Purpose

`yeying-github` implements the YeYing community fork delivery flow: develop on the contributor fork's `main` branch, publish to `origin/main`, and then reuse or create a pull request into the community `upstream/main` branch.

### Transport Modes

- `api`: recreate and publish local commits through the GitHub API when `git push`, SSH, or GitHub CLI is restricted.
- `git`: prefer the target repository's existing `scripts/sync.sh` and `scripts/pr.sh`.

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

Fields:

- `mode`: `api` publishes commits with the GitHub API; `git` uses repository Git/gh scripts.
- `sync_script`: repository-relative or absolute sync script used in Git mode. Default: `scripts/sync.sh`.
- `pr_script`: repository-relative or absolute pull-request script used in Git mode. Default: `scripts/pr.sh`.
- `origin_token`: reads the fork and updates `origin/main` in API mode.
- `upstream_token`: reads the PR head/base repositories and lists, creates, or updates pull requests on upstream.

#### Obtaining GitHub tokens

Open GitHub **Settings → Developer settings → Personal access tokens** and create a fine-grained token or, when a private cross-owner PR cannot be represented by one fine-grained resource owner, an appropriately controlled classic token or GitHub App credential.

- The origin credential needs access to the contributor fork and permission to read/write repository contents.
- The upstream credential needs read access to both PR refs and pull-request read/write permission on the community repository.
- For a PR between two private repositories owned by different accounts or organizations, a fine-grained token restricted to one resource owner may not see both sides. Use one approved credential that can read both repositories and manage upstream pull requests.
- Create the narrowest practical repository selection and expiry. Revoke or rotate the credential when the delivery environment changes.

GitHub shows a newly created PAT value only at creation time. Store it directly in the protected local file; do not paste it into shell history, issue text, PR bodies, or repository files.

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

The Skill deliberately ignores ambient `GH_TOKEN`, `GITHUB_TOKEN`, and `UPSTREAM_TOKEN` as configuration. Git mode may inject the configured `upstream_token` as `GH_TOKEN` only inside a child `gh`/`pr.sh` process for compatibility.

Validate configuration and remote state without writing:

```bash
python3 scripts/github_delivery.py --mode api --dry-run \
  --title "docs(scope): describe the complete delivery"
```

### Safety

The Skill does not force-push, merge pull requests, change branch protection, add collaborators, or change repository visibility. Never print token values. Additional details are in [`references/configuration.md`](references/configuration.md).
