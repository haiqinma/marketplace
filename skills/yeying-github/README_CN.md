# 夜莺 GitHub 交付

[English](README.md)

### 用途

`yeying-github` 把贡献者个人 fork 的 `main` 发布到 `origin/main`，再复用或创建指向社区 `upstream/main` 的准确 PR。公共和私有 fork network 都支持，并可选择 GitHub API 或仓库现有 Git/gh 脚本。

### 配置

默认配置文件为 `~/.yeying/skills/github/config.toml`。其中可能保存 PAT、GitHub App 用户令牌和刷新令牌，因此权限必须保持为 `0600`。

```toml
[github]
mode = "api"                  # api | git
visibility = "auto"           # auto | public | private
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"

[github.public]
provider = "pat"              # pat | github_app
origin_token = "<公共个人 fork PAT>"
upstream_token = "<公共社区 PR PAT>"

[github.private]
provider = "pat"              # pat | github_app
origin_token = "<私有 fork classic PAT>"
upstream_token = "<私有跨仓库 PR classic PAT>"
```

公共和私有认证配置是强制隔离的，两边不会互相回退。旧版 `[github].origin_token` 和 `[github].upstream_token` 仅作为公共 profile 的兼容入口，建议迁移到 `[github.public]`。

配置文件选择优先级：

1. `--config /绝对路径/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

传输方式选择优先级：

1. `--mode api|git`
2. `YEYING_GITHUB_MODE`
3. `[github].mode`
4. 默认 `api`

仓库可见性选择优先级：

1. `--visibility auto|public|private`
2. `YEYING_GITHUB_VISIBILITY`
3. `[github].visibility`
4. 默认 `auto`

`auto` 会先匿名检查两端仓库。如果两端都是公共仓库，则选择 `[github.public]`；否则选择 `[github.private]` 并使用私有凭证验证两端。显式 `public` 或 `private` 用于断言预期状态。每次执行都会输出传输模式、最终可见性和认证 provider，但不会输出凭证。

### 选择矩阵

| 仓库 | API 模式 | Git 模式 |
| --- | --- | --- |
| 公共 | 公共 `origin_token` 更新个人 fork；公共 `upstream_token` 管理 PR | Git 凭证推送 fork；公共 `upstream_token` 只传给 `pr.sh`/`gh` |
| 私有 PAT | 私有 `origin_token` 更新 fork；私有 `upstream_token` 必须读取两端并管理 PR | SSH/HTTPS 凭证访问两个 remote；私有 `upstream_token` 管理 PR |
| 私有 GitHub App | Device Flow 登录后，同一个 GitHub App 用户令牌执行 API 写入和 PR 操作 | Git 仍使用 SSH/HTTPS；App 用户令牌传给 `pr.sh`/`gh` |

环境限制 `git push`、SSH 或 `gh` 时选择 `api`；仓库已经有可靠的 `scripts/sync.sh`、`scripts/pr.sh` 和 Git 凭证时选择 `git`。TOML 中的 Token 永远不会用于认证 `git fetch` 或 `git push`。

### 使用 Classic PAT 提交私有 PR

可以。Classic PAT 能够从私有 fork 向私有 upstream 创建 PR，但必须同时满足以下条件：

1. 进入 GitHub **Settings -> Developer settings -> Personal access tokens -> Tokens (classic)**。
2. 创建有明确有效期、包含 `repo` scope 的 Token。没有 scope 的 classic PAT 只能读取公共信息。
3. 组织启用 SAML SSO 时，为该组织授权 PAT；组织本身也必须允许 classic PAT。
4. PAT 所属用户必须能读取两个私有仓库、推送个人 fork，并在 upstream 创建 PR。
5. 组织、企业和仓库策略必须允许私有 fork，而且 origin 必须是同一 fork network 中的真实 fork。
6. 凭证只写在 `[github.private]`。API 模式下，两个私有字段使用同一个经过批准的 classic PAT，是跨 owner 场景最稳定的配置。
7. 正式交付前先执行私有 dry-run：

```bash
python3 scripts/github_delivery.py --mode api --visibility private --dry-run \
  --title "feat(scope): 准确描述私有仓库交付内容"
```

Skill 会复用开放 PR，或者调用 `POST /repos/{upstream_owner}/{repo}/pulls`，其中 `head = "{origin_owner}:main"`、`base = "main"`。`403` 通常表示组织策略、SSO 或权限失败；`404` 通常表示凭证看不到私有仓库；`422` 通常表示两端不属于兼容的 fork network、分支没有差异，或 head 无法解析。

GitHub 通常推荐 fine-grained PAT，但它绑定单一 resource owner。私有 fork 与 upstream 分属不同账号或组织时，一个 fine-grained PAT 可能无法同时看到两端。因此，这个特定的跨 owner 工作流更适合受控的 classic PAT 或 GitHub App user access token。

### GitHub App

Skill 已内置基于 GitHub App user-to-server Device Flow 的认证。选择这种方式是有意的：installation access token 一小时后过期，并且只属于一个 installation，无法可靠横跨“个人私有 fork installation”和“社区组织 installation”；GitHub App user access token 则可以访问“用户有权访问”且“App 已安装”的仓库交集。

创建和配置 App：

1. 进入 **Settings -> Developer settings -> GitHub Apps -> New GitHub App**。
2. 配置仓库权限：**Metadata: Read**、**Contents: Read and write**、**Pull requests: Read and write**。
3. 启用 **Device Flow**。建议保持 user-to-server Token 过期功能开启，这样 Skill 会得到八小时用户令牌和 refresh token。
4. 将 App 安装到个人 fork 所在账号或组织，以及社区 upstream 所在组织，并选择需要的仓库。
5. 执行授权的 GitHub 用户本身也必须能够访问两端仓库。
6. 在配置中填写 App 的 Client ID：

```toml
[github.private]
provider = "github_app"

[github.private.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

7. 启动 Device Flow 登录：

```bash
python3 scripts/github_app_login.py --visibility private
```

命令会显示 GitHub 验证地址和一次性验证码。授权成功后，Skill 会把 `user_token`、`refresh_token` 和 `expires_at` 写回同一个受保护 TOML 文件。交付时会自动刷新即将过期的令牌；令牌不会打印，也不会出现在命令参数中。

公共 profile 同样可以选择 `github_app`，不过公共仓库通常使用 PAT 更简单。Skill 有意不使用 PEM 私钥加 installation token 来处理跨 owner 私有 PR；这种方式更适合另行设计的服务端自动化，而且所有目标仓库必须处在对应 installation 的访问边界内。

GitHub 官方参考：

- [管理 Personal Access Token](https://docs.github.com/zh/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [创建 Pull Request REST API](https://docs.github.com/zh/rest/pulls/pulls#create-a-pull-request)
- [GitHub App 代表用户认证](https://docs.github.com/zh/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-with-a-github-app-on-behalf-of-a-user)
- [生成 GitHub App user access token](https://docs.github.com/zh/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app)
- [Installation access token](https://docs.github.com/zh/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app)

### 安全边界

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

Skill 不会把环境中的 `GH_TOKEN`、`GITHUB_TOKEN` 或 `UPSTREAM_TOKEN` 当作配置来源，也不会强制推送、合并 PR、修改仓库可见性、修改分支保护或添加协作者。实现细节见 [`references/configuration.md`](references/configuration.md)。
