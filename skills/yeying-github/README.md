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
origin_token = "<public fork PAT>"
upstream_token = "<public upstream PR PAT>"

[github.private]
provider = "pat"              # pat | github_app
origin_token = "<private fork classic PAT>"
upstream_token = "<private cross-repository PR classic PAT>"
```

Public and private credentials are intentionally isolated. There is no fallback from one profile to the other. Legacy `[github].origin_token` and `[github].upstream_token` values are accepted only as a public-profile compatibility path and should be migrated.

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
| Public | Public `origin_token` writes the fork; public `upstream_token` manages the PR | Git credentials push the fork; public `upstream_token` is passed only to `pr.sh`/`gh` |
| Private with PAT | Private `origin_token` writes the fork; private `upstream_token` must read both repositories and manage the PR | SSH/HTTPS credentials access both remotes; private `upstream_token` manages the PR |
| Private with GitHub App | One GitHub App user token is used for API writes and PR operations after Device Flow login | Git still uses SSH/HTTPS; the App user token is passed to `pr.sh`/`gh` |

Choose `api` where `git push`, SSH, or `gh` is restricted. Choose `git` where repository `scripts/sync.sh` and `scripts/pr.sh` plus Git credentials are already reliable. TOML tokens never authenticate `git fetch` or `git push`.

### Private Pull Requests With A Classic PAT

Yes, a classic PAT can create a pull request from a private fork to its private upstream.

1. In GitHub, open **Settings -> Developer settings -> Personal access tokens -> Tokens (classic)**.
2. Create a time-limited token with the `repo` scope. A no-scope token can read only public information.
3. If the organization uses SAML SSO, authorize the PAT for that organization. The organization must also permit classic PAT access.
4. Confirm that the PAT owner can read both private repositories, push the personal fork, and create pull requests in upstream.
5. Confirm that organization, enterprise, and repository policies allow private forking and that origin is an actual fork in the same network.
6. Put the credential only under `[github.private]`. For API mode, using the same approved classic PAT for both private fields is the most reliable cross-owner setup.
7. Run a private dry-run before delivery:

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
