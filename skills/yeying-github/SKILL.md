---
name: yeying-github
description: Publish YeYing repository work from a contributor fork's main branch to origin/main, then reuse or create an accurate pull request into community upstream/main. Use when delivery needs global GitHub defaults with optional overrides selected by upstream repository name, and must switch between native Git/gh scripts and GitHub API transport.
---

# YeYing GitHub Delivery

Use this Skill for the YeYing fork workflow:

```text
local main -> personal origin/main -> community upstream/main PR
```

Development happens directly on the contributor fork's `main` branch. Do not create a temporary feature branch unless the user explicitly changes this workflow. Require distinct `origin` and `upstream` GitHub remotes, and require both source and base branches to be `main`.

## Configuration Model

Read [references/configuration.md](references/configuration.md) when selecting transport, credentials, or a project override.

Use `[github]` as the default configuration for every repository. Add `[github.projects.<repository>]` only when an upstream repository needs different transport, scripts, or credentials. The project key must equal the repository name parsed from the current `upstream` Git remote, case-insensitively; do not duplicate `origin` or `upstream` in the configuration.

- Treat the actual Git remotes as the only source of repository identity and PR routing.
- Match an upstream remote resolving to `<owner>/<repository>` with `[github.projects.<repository>]`.
- Use `[github]` when no project key matches.
- Project scalar settings override global defaults individually.
- If a project declares any authentication field, its authentication replaces the global authentication as a unit. Never combine a project `fork_token` with a global `pull_request_token`, or the reverse.
- If a project declares no authentication fields, it inherits the complete global authentication.
- Reject the removed `[github.public]` and `[github.private]` credential profiles.
- Reject removed project `origin` and `upstream` fields instead of silently ignoring them.

Two upstream owners with the same repository name intentionally select the same project key. When those repositories need different credentials, use separate config files selected with `--config` or `YEYING_GITHUB_CONFIG` rather than adding repository mapping fields.

Infer authentication from the selected default or project configuration. Non-empty `fork_token` or `pull_request_token` selects PAT authentication; a `github_app` subtable selects GitHub App authentication. Reject configurations containing both non-empty PAT credentials and a GitHub App table. Reject shared `token`, `provider`, `origin_token`, and `upstream_token` fields.

## Repository Access And API Quota

Do not configure or probe repository visibility. It does not select credentials or change the delivery algorithm. Let the actual GitHub operations verify repository access with the credential responsible for that operation.

GitHub tokens are not consumed like one-time secrets. API publication and PR operations consume rate-limit quota. Authenticated REST requests commonly use a 5,000-request-per-hour user quota; exact limits depend on GitHub account and App policy.

## Transport

- `api`: use `scripts/github_api_push.py` when `git push`, SSH, or `gh` is blocked or unreliable. It recreates committed objects through GitHub APIs, verifies the final tree, updates `origin/main`, and reuses or creates the upstream PR. It still uses local read-only Git commands.
- `git`: prefer the target repository's existing `scripts/sync.sh` and `scripts/pr.sh`. The wrapper calls them non-interactively with explicit PR metadata.

The default is `api`. Override it with `--mode`, `YEYING_GITHUB_MODE`, a matched project setting, or `[github].mode`, in that order.

## Credentials

- `fork_token` publishes already committed objects and updates personal `origin/main` in API mode. Git mode does not use it because Git transport authenticates through SSH or an HTTPS credential helper.
- `pull_request_token` reads required repository and PR data and lists, creates, or updates the community PR.
- When one classic PAT covers both roles, place the same value in both explicit fields.
- For a public cross-owner fork, prefer a classic PAT with only `public_repo`.
- For a private cross-owner fork PR, prefer a controlled classic PAT with `repo` or a GitHub App user-to-server token that can access both repositories.
- Add `workflow` only when committed changes modify `.github/workflows/`.

For GitHub App authentication, run `scripts/github_app_login.py --project default` for the global App or `--project <name>` for a project App. The App must be installed on both repository owners, the authorizing user must access both repositories, and the App needs Metadata read, Contents read/write, and Pull requests read/write permissions.

For a private cross-owner fork, prefer a project-specific configuration containing one Classic PAT owned by the fork owner, with `repo` scope, written explicitly to both `fork_token` and `pull_request_token`. Complete organization approval and SAML SSO authorization when required. Before the first private delivery, run `scripts/github_access_check.py` from the target repository. Require it to verify the GitHub fork parent, fork publishing access, both repositories through the PR credential, and the private head comparison. A PR credential that can read upstream but returns 404 for the private origin cannot create a reliable cross-repository PR.

## Workflow

1. Inspect `git status`, `main`, `origin`, `upstream`, and the complete `upstream/main..HEAD` commit and diff range.
2. Verify that all changes intended for delivery are committed. Never include unrelated working-tree changes. API mode may use `--allow-dirty` only after those changes are understood; Git mode remains clean-worktree only because repository scripts may rebase.
3. Write a specific PR title that summarizes the complete delivered delta.
4. Run the wrapper from the target repository:

```bash
python3 /path/to/yeying-github/scripts/github_delivery.py \
  --title "feat(scope): describe the delivered capability"
```

5. Run with `--dry-run` first for API delivery or whenever remote state is uncertain.
6. Execute the real command only after the user authorizes the external write. Verify `HEAD`, `origin/main`, tree equality, and the final PR URL.

Use `--body-file` when a reviewed PR body should be applied. In API mode, an explicitly supplied `--body` or `--body-file` updates the body of an existing PR; when neither is supplied, the wrapper builds a concise body from the commit range and preserves any existing human-maintained body. Existing PRs are reused and their title is corrected when it differs from the requested title.

## Permission Boundary

Read PATs and GitHub App secrets only from `~/.yeying/skills/github/config.toml` or the file selected with `--config`/`YEYING_GITHUB_CONFIG`. Do not use ambient `GH_TOKEN`, `GITHUB_TOKEN`, or `UPSTREAM_TOKEN` as configuration. A config containing tokens must be mode `0600` or stricter.

Never print tokens, add collaborators, alter repository visibility, force-update refs, merge a PR, or change branch protection unless the user explicitly requests that separate operation.
