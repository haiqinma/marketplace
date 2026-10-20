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
token = "<公共仓库使用的 classic PAT，只有 public_repo scope>"

[github.private]
provider = "pat"              # pat | github_app
token = "<同时访问私有 fork 和 upstream 的 classic PAT>"
```

每个 profile 可以配置一个共享 `token`，也可以分别配置 `origin_token` 和 `upstream_token`。解析顺序是：角色专用字段优先，没有专用字段时回退到同一 profile 的 `token`。公共和私有认证配置强制隔离，绝不会互相回退。旧版 `[github].origin_token` 和 `[github].upstream_token` 仅作为公共 profile 的兼容入口，建议迁移。

#### 三个 Token 字段究竟做什么

字段名描述的是 GitHub remote 的角色，不是 Git 操作。尤其要注意：`git commit` 只写本地 Git 数据库，**不需要任何 GitHub Token**。

| 字段 | API 模式 | Git 模式 | 所需访问能力 |
| --- | --- | --- | --- |
| `token` | 同一凭证同时作为 origin 和 upstream 凭证 | 仅作为 PR 凭证；不参与 Git 传输 | 取决于 profile，必须覆盖实际使用的两个角色 |
| `origin_token` | 发布已经存在的本地 commit/tree/blob，并更新个人 `origin/main` | 不使用 | 对个人 fork 的 Metadata read、Contents read/write |
| `upstream_token` | 读取两端仓库，查询、创建或更新社区 upstream 的 PR | 临时传给 `pr.sh`/`gh`；`git push` 不使用 | upstream 的 Metadata read、Pull requests read/write；私有 PR 时还必须看见两端仓库 |

因此，“一个用来 commit、一个用来提交 PR”并不准确。更准确的说法是：“一个用于把本地已有提交发布到 origin，一个用于管理 upstream PR”。如果一个 PAT 同时具备两端权限，只配置一次 `token` 即可。

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
| 公共、普通外部贡献者 | 推荐一个只有 `public_repo` scope 的 classic PAT，写入 `token` | Git 凭证推送 fork；共享 `token` 只传给 `pr.sh`/`gh` |
| 公共、可选择两端 resource owner | 可以分别使用两个 fine-grained PAT | Git 凭证推送 fork；`upstream_token` 只传给 `pr.sh`/`gh` |
| 私有、同一 resource owner | 可使用一个覆盖两个仓库的 fine-grained PAT，写入 `token` | Git 使用 SSH/HTTPS；共享 `token` 仅用于 PR |
| 私有、跨 resource owner | 推荐一个具有 `repo` scope 的 classic PAT，写入 `token`；也可使用 GitHub App | Git 使用 SSH/HTTPS；共享 `token` 仅用于 PR |
| 私有 GitHub App | Device Flow 登录后，同一个 GitHub App 用户令牌执行 API 写入和 PR 操作 | Git 仍使用 SSH/HTTPS；App 用户令牌传给 `pr.sh`/`gh` |

环境限制 `git push`、SSH 或 `gh` 时选择 `api`；仓库已经有可靠的 `scripts/sync.sh`、`scripts/pr.sh` 和 Git 凭证时选择 `git`。TOML 中的 Token 永远不会用于认证 `git fetch` 或 `git push`。

### Fine-grained PAT 怎么配置

GitHub 的 **Fine-grained tokens** 绑定一个 resource owner，只能选择该 owner 名下的仓库。拥有另一个账号仓库的管理员或协作者权限，并不会让那个账号自动出现在自己的 resource owner 列表中。

Fine-grained PAT 很适合发布自己名下的 fork：

```toml
[github.public]
provider = "pat"
origin_token = "<resource owner 为个人账号、只选择个人 fork>"
upstream_token = "<另一个能够在社区 upstream 创建 PR 的凭证>"
```

- `origin_token`：Repository access 只选择个人 fork；Repository permissions 设置 **Contents: Read and write**。Metadata read 会随仓库访问自动提供。
- `upstream_token` 只有在 GitHub 允许你选择社区组织作为 resource owner，且组织批准该 Token 时，才能使用社区 upstream 的 fine-grained PAT；选择 upstream 仓库并设置 **Pull requests: Read and write**。

普通外部贡献者通常不能为另一个个人账号或自己并非成员的组织创建这种 upstream fine-grained PAT。因此，公共跨 owner fork 更简单且更可靠的配置是一个只有 `public_repo` scope 的 classic PAT，写入 `[github.public].token`。它不会访问私有仓库。

私有 fork 和 upstream 属于同一个 resource owner 时，可以让一个 fine-grained PAT 选择两个仓库：

```toml
[github.private]
provider = "pat"
token = "<选择两个私有仓库的 fine-grained PAT>"
```

这个 Token 需要 **Contents: Read and write** 和 **Pull requests: Read and write**。如果两个私有仓库分属个人账号与社区组织，一个 fine-grained PAT 通常无法跨越两个 resource owner；不要误以为在配置中复制同一个值就会扩大它的仓库边界。

### Tokens (classic) 怎么配置

Classic PAT 可以覆盖跨 owner fork：公共仓库使用 `public_repo`，私有仓库使用 `repo`。它的 scope 不是逐仓库授权，因此要严格按可见性分开配置。

1. 进入 GitHub **Settings -> Developer settings -> Personal access tokens -> Tokens (classic)**。
2. 填写容易识别用途的 Note，并设置尽可能短且符合组织策略的有效期，通常建议 30 至 90 天；到期前轮换。
3. 如果 origin 和 upstream 都是公共仓库，只勾选 `public_repo`，配置到 `[github.public].token`。
4. 如果需要访问任一私有仓库，勾选顶层 `repo`，配置到 `[github.private].token`。GitHub 会自动勾选它下面的 `repo:status`、`repo_deployment`、`public_repo`、`repo:invite` 和 `security_events`，这是正常现象；选择顶层 `repo` 时不能单独取消这些子项。
5. 只有本次交付确实会修改 `.github/workflows/` 下的 GitHub Actions 工作流文件时，才额外勾选 `workflow`。
6. **不要勾选** `admin:enterprise`、`write:network_configurations`、`admin:org`、`delete_repo`、`write:packages`、`admin:repo_hook`、`admin:org_hook`、`user`、`audit_log`、`codespace`、`copilot`、`project`、`admin:gpg_key` 或 `admin:ssh_signing_key`。这些权限与发布 fork 和创建 PR 无关。
7. 组织启用 SAML SSO 时，在 Token 创建后点击 **Configure SSO** 为社区组织授权；组织本身也必须允许 classic PAT。
8. PAT 所属用户必须能读取目标仓库、推送个人 fork，并在 upstream 创建 PR。
9. 私有 fork 还要求组织、企业和仓库策略允许私有 fork，而且 origin 必须是同一 fork network 中的真实 fork。
10. 公共和私有 Token 分别保存：

```toml
[github.public]
provider = "pat"
token = "<classic PAT with public_repo scope>"

[github.private]
provider = "pat"
token = "<classic PAT with repo scope>"
```

就你截图中的选择而言：如果是私有仓库，保留 `repo`；如果两端都为公共仓库，应取消顶层 `repo`，只保留它的 `public_repo` 子 scope。若不修改 Actions 工作流则不要选 `workflow`。无论公共还是私有，都取消 `admin:enterprise` 和 `write:network_configurations`，其余无关 scope 也不要选。这个 Skill 不需要企业管理权限或托管计算网络配置权限。

Classic PAT 的 `repo` 是一个较宽的授权，无法像 fine-grained PAT 那样逐仓库收窄。请把它视为高敏感凭证：只存放在 `0600` 配置文件中，不写入仓库，不输出到日志，设置有效期并定期轮换。

创建后还必须满足以下运行条件：

1. 组织允许 classic PAT；若需要，Token 已完成审批。
2. 如果启用了 SAML SSO，Token 已针对 upstream 组织授权。
3. PAT 用户能访问两个私有仓库，且私有 fork network 策略允许从 origin 向 upstream 提 PR。
4. 正式交付前先执行私有 dry-run：

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
