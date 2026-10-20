# 夜莺 GitHub 交付

[English](README.md)

### 用途

`yeying-github` 把贡献者个人 fork 的 `main` 发布到 `origin/main`，再复用或创建指向社区 `upstream/main` 的 PR。公共和私有 fork network 都支持，并可选择 GitHub API 或仓库现有的 Git/gh 脚本。

### 配置

默认配置文件：

```text
~/.yeying/skills/github/config.toml
```

推荐完整配置：

```toml
[github]
mode = "api"                  # api | git
visibility = "auto"           # auto | public | private
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"

[github.public]
provider = "pat"              # pat | github_app
fork_token = "<发布个人公共 fork 的 PAT>"
pull_request_token = "<创建公共 upstream PR 的 PAT>"

[github.private]
provider = "pat"              # pat | github_app
fork_token = "<发布个人私有 fork 的 PAT>"
pull_request_token = "<读取两端私有仓库并创建 PR 的 PAT>"
```

PAT profile 只接受 `fork_token` 和 `pull_request_token`。没有共享 `token`，也不接受旧字段或放在 `[github]` 根表中的凭证。发现不支持的字段时，Skill 会立即报错并列出允许的字段，避免配置被静默忽略。

### 两个字段的职责

| 字段 | API 模式 | Git 模式 | 权限要求 |
| --- | --- | --- | --- |
| `fork_token` | 发布本地已经存在的 commit/tree/blob，并更新个人 `origin/main` | 不使用 | 个人 fork 的 Metadata read、Contents read/write |
| `pull_request_token` | 读取仓库元数据，查询、创建或更新社区 upstream PR | 临时传给 `pr.sh`/`gh` | upstream 的 Metadata read、Pull requests read/write；私有交付时必须读取两端私有仓库 |

`git commit` 始终是本地操作，不需要 GitHub Token。`fork_token` 不是“commit Token”，它只负责把已经提交的本地对象发布到个人 fork。

如果同一个 Classic PAT 能完成两个职责，把同一个值明确写入两个字段：

```toml
[github.public]
provider = "pat"
fork_token = "<同一个 Classic PAT>"
pull_request_token = "<同一个 Classic PAT>"
```

这里有意不做隐式共享或回退。两个字段分别对应两条执行路径，权限错误能够直接定位到 fork 发布或 PR 管理。

### API 与 Git 模式

API 模式：

```toml
[github]
mode = "api"
```

- `fork_token` 必填，用于更新个人 `origin/main`。
- `pull_request_token` 必填，用于仓库检查和 PR 操作。
- 适合 `git push`、SSH 或 `gh` 被环境限制的场景。

Git 模式：

```toml
[github]
mode = "git"
```

- `scripts/sync.sh` 使用 SSH Key 或 HTTPS credential helper 执行 fetch/push。
- `fork_token` 不参与 Git 传输，可以留空。
- `pull_request_token` 用于 `scripts/pr.sh` 或 `gh` 创建和更新 PR。

### 自动识别公共与私有仓库

推荐保持：

```toml
[github]
visibility = "auto"
```

Skill 先匿名读取 origin 和 upstream 元数据。两端都能匿名读取且为 public 时选择 `[github.public]`；否则加载 `[github.private].pull_request_token` 重新验证两端。认证后仍不可见时会停止，不会把“仓库不存在”“Token 无权限”和“私有仓库”混为一谈。

显式 `public` 或 `private` 是断言，不会跳过 GitHub 元数据验证。两端可见性不同也会停止。

### 公共仓库 PAT

普通外部贡献者最简单的方案是创建一个 **Token (classic)**，只选择 `public_repo`，然后把同一个值填入两个字段：

```toml
[github.public]
provider = "pat"
fork_token = "<Classic PAT: public_repo>"
pull_request_token = "<Classic PAT: public_repo>"
```

如果使用两个 Fine-grained PAT：

```toml
[github.public]
provider = "pat"
fork_token = "<个人账号、只选择个人 fork>"
pull_request_token = "<社区组织、只选择 upstream>"
```

- `fork_token`：个人 fork，**Contents: Read and write**。Metadata read 自动提供。
- `pull_request_token`：社区 upstream，**Pull requests: Read and write**。Metadata read 自动提供。

Fine-grained PAT 绑定一个 resource owner。成为另一个个人账号仓库的管理员或协作者，并不会让那个个人账号出现在自己的 resource owner 列表中。只有 GitHub 允许贡献者选择社区组织且组织批准 Token 时，社区 upstream 的 Fine-grained PAT 才可行。

### 私有仓库 PAT

私有 fork 与 upstream 分属不同 resource owner 时，推荐一个 **Token (classic)**，选择顶层 `repo`，并把同一值填入两个字段：

```toml
[github.private]
provider = "pat"
fork_token = "<Classic PAT: repo>"
pull_request_token = "<Classic PAT: repo>"
```

该 PAT 所属用户必须：

1. 能读取两个私有仓库。
2. 能更新个人 fork。
3. 能从个人 fork 向 upstream 创建 PR。
4. 在需要时完成组织审批和 SAML SSO 授权。
5. 位于组织、企业和仓库策略允许的私有 fork network 中。

如果两个私有仓库属于同一个 resource owner，也可以使用选择了两个仓库、具有 Contents read/write 和 Pull requests read/write 的 Fine-grained PAT。

### Tokens (classic) 勾选清单

两端都是公共仓库：

```text
[x] public_repo
```

任一端是私有仓库：

```text
[x] repo
```

选择顶层 `repo` 后，GitHub 会自动选择 `repo:status`、`repo_deployment`、`public_repo`、`repo:invite`、`security_events` 等子项，这是正常行为。

只有提交确实修改 `.github/workflows/` 时才额外选择：

```text
[x] workflow
```

不要选择：

```text
[ ] admin:enterprise
[ ] write:network_configurations
[ ] admin:org
[ ] delete_repo
[ ] packages、hooks、user、audit log、codespaces、Copilot、projects
[ ] GPG Key 或 SSH Signing Key 管理权限
```

Classic PAT 不能像 Fine-grained PAT 一样按仓库收窄。请设置较短有效期，通常为 30 至 90 天，并按组织策略轮换。

### GitHub App

GitHub App 使用 user-to-server Device Flow，一个 App 用户令牌同时承担 fork 和 PR 两个职责，不配置 PAT 字段：

```toml
[github.private]
provider = "github_app"

[github.private.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

App 需要 **Metadata: Read**、**Contents: Read and write**、**Pull requests: Read and write**，并安装到 fork 和 upstream 两边。授权用户本身也必须访问两端仓库。

登录命令：

```bash
python3 scripts/github_app_login.py --visibility private
```

Skill 会把 `user_token`、`refresh_token` 和 `expires_at` 写回受保护的配置文件，并在需要时自动刷新。跨 owner 私有 PR 不使用 installation access token，因为它只属于一个 installation 且一小时过期。

### 配置优先级

配置文件：

1. `--config /绝对路径/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

传输模式：

1. `--mode api|git`
2. `YEYING_GITHUB_MODE`
3. `[github].mode`
4. 默认 `api`

可见性：

1. `--visibility auto|public|private`
2. `YEYING_GITHUB_VISIBILITY`
3. `[github].visibility`
4. 默认 `auto`

### 安全与运行

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

包含任一 Token 的配置文件必须是 `0600` 或更严格。Skill 不读取环境中的 `GH_TOKEN`、`GITHUB_TOKEN` 或 `UPSTREAM_TOKEN` 作为配置，不打印 Token，不强推、不合并 PR，也不修改仓库可见性、分支保护或协作者。

先 dry-run：

```bash
python3 scripts/github_delivery.py --mode api --visibility auto --dry-run \
  --title "chore(scope): accurately describe the delivery"
```

确认后执行正式交付：

```bash
python3 scripts/github_delivery.py \
  --title "chore(scope): accurately describe the delivery"
```

实现细节见 [`references/configuration.md`](references/configuration.md)。

GitHub 官方参考：

- [管理 Personal Access Token](https://docs.github.com/zh/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [创建 Pull Request REST API](https://docs.github.com/zh/rest/pulls/pulls#create-a-pull-request)
- [GitHub App 代表用户认证](https://docs.github.com/zh/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user)
