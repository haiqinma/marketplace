# YeYing GitHub Delivery

[简体中文](README_CN.md)

### Purpose

`yeying-github` publishes a contributor fork's `main` branch to `origin/main`, then reuses or creates an accurate pull request into community `upstream/main`. It supports public and private fork networks through either GitHub API transport or repository Git/gh scripts.

### Configuration

The default configuration file is `~/.yeying/skills/github/config.toml`. Keep it mode `0600` because it may contain PATs, GitHub App user tokens, and refresh tokens.

```toml
[github]
mode = "api"                  # api | git
visibility = "auto"           # auto | public | private
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"

[github.public]
provider = "pat"              # pat | github_app
token = "<classic PAT with only the public_repo scope>"

[github.private]
provider = "pat"              # pat | github_app
token = "<classic PAT that can access both private repositories>"
```

Each profile may define one shared `token`, or separate `origin_token` and `upstream_token` values. A role-specific field wins; an omitted role falls back to `token` in the same profile. Public and private credentials are strictly isolated and never fall back to each other. Legacy `[github].origin_token` and `[github].upstream_token` values are accepted only as a public-profile compatibility path and should be migrated.

#### What Each Token Field Actually Does

The field names describe GitHub remote roles, not Git operations. In particular, `git commit` writes only to the local Git database and **never requires a GitHub token**.

| Field | API mode | Git mode | Required access |
| --- | --- | --- | --- |
| `token` | Shared fallback credential for both origin and upstream roles | Used only for the PR role; never used for Git transport | Must cover every role actually used by the selected profile |
| `origin_token` | Publishes already-created local commit/tree/blob objects and updates personal `origin/main` | Unused | Metadata read and Contents read/write on the personal fork |
| `upstream_token` | Reads both repositories and lists, creates, or updates the upstream PR | Passed temporarily to `pr.sh`/`gh`; never used by `git push` | Metadata read and Pull requests read/write on upstream; for private PRs it must also see both repositories |

It is therefore inaccurate to call these “the commit token” and “the PR token.” The first publishes an existing local commit to origin; the second manages the upstream PR. When one PAT legitimately covers both repositories, configure it once as `token`.

Configuration-file selection:

1. `--config /absolute/path/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

Transport selection:

1. `--mode api|git`
2. `YEYING_GITHUB_MODE`
3. `[github].mode`
4. default `api`

Visibility selection:

1. `--visibility auto|public|private`
2. `YEYING_GITHUB_VISIBILITY`
3. `[github].visibility`
4. default `auto`

`auto` first checks both repositories without authentication. If both are public, it selects `[github.public]`. Otherwise it selects `[github.private]` and verifies both repositories with that profile. Explicit `public` or `private` asserts the expected state. Every run prints the selected transport, visibility, and provider without printing credentials.

### Selection Matrix

| Repositories | API mode | Git mode |
| --- | --- | --- |
| Public, ordinary external contributor | Prefer one classic PAT with only `public_repo`, stored as `token` | Git credentials push the fork; shared `token` is passed only to `pr.sh`/`gh` |
| Public, both resource owners selectable | Two separate fine-grained PATs may be used | Git credentials push the fork; `upstream_token` is passed only to `pr.sh`/`gh` |
| Private, same resource owner | One fine-grained PAT selecting both repositories can be stored as `token` | Git uses SSH/HTTPS; shared `token` is used only for the PR |
| Private, different resource owners | Prefer one classic PAT with `repo` scope stored as `token`, or use GitHub App authentication | Git uses SSH/HTTPS; shared `token` is used only for the PR |
| Private with GitHub App | One GitHub App user token is used for API writes and PR operations after Device Flow login | Git still uses SSH/HTTPS; the App user token is passed to `pr.sh`/`gh` |

Choose `api` where `git push`, SSH, or `gh` is restricted. Choose `git` where repository `scripts/sync.sh` and `scripts/pr.sh` plus Git credentials are already reliable. TOML tokens never authenticate `git fetch` or `git push`.

### Configuring Fine-Grained PATs

A GitHub **Fine-grained token** is bound to one resource owner and can select only repositories owned by that owner. Being an administrator or collaborator on a repository owned by another personal account does not make that account available as your token's resource owner.

Fine-grained PATs work well for publishing a fork owned by your account:

```toml
[github.public]
provider = "pat"
origin_token = "<resource owner: personal account; repository: personal fork>"
upstream_token = "<another credential that can create the upstream PR>"
```

- For `origin_token`, select only the personal fork and grant **Contents: Read and write**. Metadata read is included with repository access.
- `upstream_token` can be a fine-grained PAT for community upstream only when GitHub lets you select the community organization as the resource owner and the organization approves the token. Select upstream and grant **Pull requests: Read and write**.

An ordinary external contributor usually cannot create that upstream fine-grained PAT for another personal account or for an organization they cannot select as resource owner. For a public cross-owner fork, the simpler reliable setup is one classic PAT with only `public_repo`, stored as `[github.public].token`. It does not grant access to private repositories.

When a private fork and upstream belong to the same resource owner, one fine-grained PAT can select both repositories:

```toml
[github.private]
provider = "pat"
token = "<fine-grained PAT selecting both private repositories>"
```

Grant **Contents: Read and write** and **Pull requests: Read and write**. If the two private repositories belong to a personal account and a different community organization, one fine-grained PAT generally cannot cross those resource-owner boundaries. Repeating the same value in two configuration fields does not expand its repository access.

### Configuring A Token (classic)

A classic PAT can cover a cross-owner fork. Use `public_repo` for public repositories and `repo` for private repositories. Classic scopes are not repository-specific, so keep public and private credentials in separate profiles.

1. In GitHub, open **Settings -> Developer settings -> Personal access tokens -> Tokens (classic)**.
2. Enter a purpose-specific Note and choose the shortest practical expiration allowed by the organization, commonly 30 to 90 days, then rotate before expiry.
3. If origin and upstream are both public, select only `public_repo` and store the token as `[github.public].token`.
4. If either repository is private, select the top-level `repo` scope and store the token as `[github.private].token`. GitHub automatically selects its `repo:status`, `repo_deployment`, `public_repo`, `repo:invite`, and `security_events` children. That is expected; those children cannot be cleared individually while `repo` remains selected.
5. Select `workflow` only when this delivery must modify GitHub Actions workflow files under `.github/workflows/`.
6. Do **not** select `admin:enterprise`, `write:network_configurations`, `admin:org`, `delete_repo`, `write:packages`, `admin:repo_hook`, `admin:org_hook`, `user`, `audit_log`, `codespace`, `copilot`, `project`, `admin:gpg_key`, or `admin:ssh_signing_key`. They are unrelated to publishing a fork and creating a PR.
7. If the organization uses SAML SSO, use **Configure SSO** after creating the token to authorize it for the community organization. The organization must also permit classic PAT access.
8. The PAT owner must be able to read the target repositories, push the personal fork, and create pull requests in upstream.
9. Private forks also require organization, enterprise, and repository policies to allow private forking, and origin must be a real fork in the same network.
10. Store public and private credentials separately:

```toml
[github.public]
provider = "pat"
token = "<classic PAT with public_repo scope>"

[github.private]
provider = "pat"
token = "<classic PAT with repo scope>"
```

For the selections shown in your screenshots: keep `repo` for private repositories. If both sides are public, clear the top-level `repo` scope and keep only its `public_repo` child. Leave `workflow` clear unless workflow files are being changed. In either case, clear `admin:enterprise` and `write:network_configurations`, and leave all other unrelated scopes clear. This Skill does not require enterprise administration or hosted-compute network configuration access.

The classic `repo` scope is broad and cannot be narrowed to selected repositories like a fine-grained PAT. Treat it as a high-sensitivity credential: keep it only in the mode-`0600` config file, never commit or log it, give it an expiration, and rotate it regularly.

Before running delivery, also confirm:

1. The organization permits classic PATs and any required approval is complete.
2. The token is SAML SSO-authorized for upstream when required.
3. The PAT user can access both private repositories and private-fork policies allow a PR from origin to upstream.
4. Run a private dry-run before delivery:

```bash
python3 scripts/github_delivery.py --mode api --visibility private --dry-run \
  --title "feat(scope): accurately describe the private delivery"
```

The Skill lists an existing PR or calls `POST /repos/{upstream_owner}/{repo}/pulls` with `head = "{origin_owner}:main"` and `base = "main"`. A `403` commonly indicates organization policy, SSO, or permission failure. A `404` commonly means the private repository is hidden from the credential. A `422` commonly indicates that the repositories are not in a compatible fork network, the branches have no diff, or the head cannot be resolved.

GitHub recommends fine-grained PATs generally, but a fine-grained PAT is bound to one resource owner. For a private fork and upstream owned by different accounts, one fine-grained PAT may not see both sides. A controlled classic PAT or GitHub App user token is therefore the practical choice for this specific cross-owner workflow.

### GitHub App

GitHub App authentication is built into this Skill using GitHub's user-to-server Device Flow. This is deliberate: an installation access token expires after one hour and is scoped to one installation, so it cannot reliably span a private personal fork installation and a separate community organization installation. A GitHub App user access token can access the intersection of repositories that the user can access and repositories where the App is installed.

Create and configure the App:

1. Open **Settings -> Developer settings -> GitHub Apps -> New GitHub App**.
2. Grant repository permissions: **Metadata: Read**, **Contents: Read and write**, and **Pull requests: Read and write**.
3. Enable **Device Flow**. Keep expiring user-to-server tokens enabled so the Skill receives an eight-hour user token and a refresh token.
4. Install the App on the contributor account or organization containing the fork and on the community organization containing upstream. Select the required repositories.
5. The authorizing GitHub user must independently have access to both repositories.
6. Configure the profile with the App's client ID:

```toml
[github.private]
provider = "github_app"

[github.private.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

7. Start Device Flow login:

```bash
python3 scripts/github_app_login.py --visibility private
```

The command displays GitHub's verification URL and a one-time code. After authorization, it stores `user_token`, `refresh_token`, and `expires_at` under `[github.private.github_app]` in the same protected TOML file. Delivery refreshes an expiring token automatically; token values are never printed or passed as command arguments.

The same provider is available under `[github.public]`, but PATs are usually simpler for public repositories. Installation-token authentication with a PEM private key is intentionally not used for cross-owner private PRs; use it only in a separate service design where every required repository is reachable through the relevant installation boundary.

Official GitHub references:

- [Managing personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [Create a pull request REST endpoint](https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request)
- [GitHub App user authentication](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user)
- [Generate a GitHub App user access token](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)
- [Installation access tokens](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)

### Safety

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

The Skill ignores ambient `GH_TOKEN`, `GITHUB_TOKEN`, and `UPSTREAM_TOKEN` as configuration. It does not force-push, merge pull requests, change repository visibility, change branch protection, or add collaborators. More implementation detail is in [`references/configuration.md`](references/configuration.md).
