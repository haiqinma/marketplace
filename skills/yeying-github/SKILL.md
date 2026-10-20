---
name: yeying-github
description: Publish YeYing repository work from a public or private contributor fork's main branch to origin/main, then reuse or create an accurate pull request into the community upstream/main. Use when GitHub delivery must switch between native Git/gh scripts and GitHub API transport because some environments restrict git push or GitHub CLI execution.
---

# YeYing GitHub Delivery

Use this Skill for the YeYing fork workflow:

```text
local main -> personal origin/main -> community upstream/main PR
```

Development happens directly on the contributor fork's `main` branch. Do not create a temporary feature branch unless the user explicitly changes this workflow. Require distinct `origin` and `upstream` GitHub remotes, and require both the source and base branch to be `main`.

## Transport And Visibility

Read [references/configuration.md](references/configuration.md) when selecting transport, repository visibility, or credentials.

- `api`: use the bundled `scripts/github_api_push.py`. Choose this when `git push`, SSH, or `gh` is blocked or unreliable. It recreates committed objects through the GitHub API, verifies the final tree, updates `origin/main`, and reuses or creates the upstream PR. It still uses local read-only Git commands to inspect commits and trees; the switch replaces Git's remote write transport, not the local repository database.
- `git`: prefer the target repository's existing `scripts/sync.sh` and `scripts/pr.sh`. The wrapper calls them with non-interactive settings and explicit PR metadata; do not replace mature repository scripts with ad hoc push or PR commands.

The default is `api`. Override it with `--mode`, `YEYING_GITHUB_MODE`, or `~/.yeying/skills/github/config.toml`.

Treat transport and visibility as independent settings:

- `visibility = "auto"` is recommended. Detect both repositories through GitHub and print the resolved `public` or `private` value before delivery.
- `visibility = "public"` or `"private"` asserts the expected access model. Stop when either repository does not match.
- Require origin and upstream to have the same visibility. Do not try to bridge a public repository and a private repository with this fork workflow.

Override visibility with `--visibility`, `YEYING_GITHUB_VISIBILITY`, or the config file. Always run the remote visibility preflight in both API and Git modes.

Keep authentication isolated by visibility:

- Read public PAT or GitHub App settings only from `[github.public]`.
- Read private PAT or GitHub App settings only from `[github.private]`.
- Never fall back from one visibility profile to the other. Legacy root tokens are public-only compatibility values.
- For a private cross-owner fork PR, prefer a controlled classic PAT with `repo` scope or the bundled GitHub App user-to-server Device Flow. A fine-grained PAT may be unable to span two resource owners.
- Do not treat an installation access token as a combined cross-owner credential; it is scoped to one installation and expires after one hour.

When `provider = "github_app"`, run `scripts/github_app_login.py --visibility public|private` before delivery. The App must be installed on both repository owners, the authorizing user must access both repositories, and the App needs Metadata read, Contents read/write, and Pull requests read/write permissions. Refresh expiring user tokens through the configured refresh token without printing them.

## Workflow

1. Inspect `git status`, `main`, `origin`, `upstream`, and the complete `upstream/main..HEAD` commit and diff range.
2. Verify that all changes intended for delivery are committed. Never include unrelated working-tree changes. API mode may use `--allow-dirty` only after those changes are understood; Git mode remains clean-worktree only because repository scripts may rebase.
3. Write a specific PR title that summarizes the complete delivered delta. Do not use generic titles such as `update`, `changes`, or the first commit subject without checking the whole range.
4. Run the wrapper from the target repository:

```bash
python3 /path/to/yeying-github/scripts/github_delivery.py \
  --title "feat(scope): describe the delivered capability"
```

5. Run with `--dry-run` first for API delivery or whenever remote state is uncertain. Confirm fast-forward safety, the commits to publish, and whether an open PR already exists.
6. Execute the real command only after the user has authorized the external write. Verify `HEAD`, `origin/main`, tree equality, and the final PR URL.

Use `--body-file` when a reviewed PR body already exists. Otherwise the wrapper builds a concise body from the commit range. Existing PRs are reused; if their title differs, the requested accurate title replaces it without overwriting a human-maintained body.

## Commands

```bash
# Configured/default transport
python3 scripts/github_delivery.py --title "fix(router): preserve provider failover state"

# Force GitHub API transport
python3 scripts/github_delivery.py --mode api --dry-run \
  --visibility auto \
  --title "docs(skills): add yeying GitHub delivery workflow"

# Force native repository scripts
python3 scripts/github_delivery.py --mode git \
  --title "feat(wallet): add recovery audit events"

# API mode with inspected, unrelated working-tree changes
python3 scripts/github_delivery.py --mode api --allow-dirty \
  --title "docs(warehouse): clarify Skill installation"
```

## Permission Boundary

Read PATs, GitHub App user tokens, and refresh tokens only from `~/.yeying/skills/github/config.toml` (or the file selected with `--config`/`YEYING_GITHUB_CONFIG`). Do not use ambient `GH_TOKEN`, `GITHUB_TOKEN`, or `UPSTREAM_TOKEN` as configuration. A config containing tokens must be mode `0600` or stricter. In private PAT mode, the selected upstream credential must read both private head and base repositories.

Never print tokens, add collaborators, alter repository visibility, force-update refs, merge a PR, or change branch protection unless the user explicitly requests that separate operation.
