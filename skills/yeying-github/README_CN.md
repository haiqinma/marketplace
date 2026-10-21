# 夜莺 GitHub 交付

[English](README.md)

### 用途

`yeying-github` 把贡献者个人 fork 的 `main` 发布到 `origin/main`，再复用或创建指向社区 `upstream/main` 的 PR。它既支持 GitHub API 交付，也支持通过仓库已有的 Git/gh 脚本交付。

### 配置

默认配置文件：

```text
~/.yeying/skills/github/config.toml
```

配置分为两层：

1. `[github]` 保存所有仓库共用的默认配置。
2. `[github.projects.<repository>]` 是可选的，当项目 key 与当前 `upstream` Git remote 中的仓库名匹配时生效。

不再按公共仓库和私有仓库拆分凭证 profile，也不再配置 `visibility`。凭证属于默认账号配置或某个具体项目，实际 GitHub 操作会直接验证这些凭证是否具备所需访问权限。

### 最小默认配置

没有匹配到项目覆盖时，所有仓库都使用下面的配置：

```toml
[github]
mode = "api"                  # api | git
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"
fork_token = "<发布个人 origin/main 的 PAT>"
pull_request_token = "<读取仓库并管理 upstream PR 的 PAT>"
```

认证方式自动推断：

- 非空 `fork_token` 或 `pull_request_token` 表示使用 PAT。
- `[github.github_app]` 子表表示使用 GitHub App。
- 非空 PAT 字段和 GitHub App 子表不能同时存在。
- 不支持 `provider`、共享 `token`、`origin_token` 或 `upstream_token`。

### 项目覆盖配置

只有某个 upstream 仓库需要不同配置时，才增加项目条目：

```toml
[github.projects.marketplace]
mode = "git"
```

项目 key 必须与 upstream 仓库名一致，匹配时不区分大小写。项目名可以包含字母、数字、`_` 和 `-`。

例如当前 remote 是：

```text
origin   -> liuppx/marketplace
upstream -> yeying-community/marketplace
```

Skill 会从实际 upstream remote 推导出 `marketplace`，然后选择 `[github.projects.marketplace]`。origin owner 和仓库名始终从实际 `origin` remote 读取，不在配置文件中重复维护。

上面的例子覆盖传输模式，继承默认脚本和凭证。空项目表没有实际作用，应直接省略。

不同 upstream owner 下的同名仓库会选择同一个项目 key。如果它们需要不同凭证，请使用不同配置文件，并通过 `--config` 或 `YEYING_GITHUB_CONFIG` 选择，不再增加仓库映射字段。

### 项目独立凭证

项目可以完整替换默认认证：

```toml
[github.projects.internal-service]
mode = "api"
fork_token = "<写入个人私有 fork 的 PAT>"
pull_request_token = "<读取两端私有仓库并创建 PR 的 PAT>"
```

认证按整体继承：

- 项目没有配置 `fork_token`、`pull_request_token` 或 `github_app` 时，完整继承全局认证。
- 项目只要声明任一认证字段，就只使用项目认证。
- 不会把项目的 `fork_token` 与全局的 `pull_request_token` 混合，也不会反向混合。
- 项目需要为所选传输模式完整配置它需要的所有凭证。

这条规则可以让凭证归属和权限错误保持明确。

### 仓库访问与 Token 消耗

Skill 不再专门探测仓库是公开还是私有。可见性既不影响凭证选择，也不改变交付算法，继续探测只会增加配置和 API 请求。

访问权限由真正需要它的操作直接验证：

- `fork_token` 在 API 模式中访问并更新个人 `origin/main`。
- `pull_request_token` 读取 upstream PR 数据并创建或更新 PR。
- GitHub App user token 同时承担两个职责。

私有仓库自然要求凭证能够读取相关仓库；公共仓库通常可以使用更小的权限，但运行时不需要单独分支。

Token 不会因为调用而被“消耗”或缩短寿命。GitHub API 操作会计入 Token 的 rate-limit 配额。普通已认证用户请求通常为每小时 5000 次，但账号、组织、企业和 App 策略可能改变实际额度。

### 两个 Token 字段的职责

| 字段 | API 模式 | Git 模式 | 权限要求 |
| --- | --- | --- | --- |
| `fork_token` | 发布本地已经存在的 commit/tree/blob，并更新个人 `origin/main` | 不使用 | 个人 fork 的 Metadata read、Contents read/write |
| `pull_request_token` | 读取所需仓库和 PR 数据，并查询、创建或更新 upstream PR | 临时传给 `pr.sh`/`gh` | upstream 的 Metadata read、Pull requests read/write；私有交付时必须读取两端仓库 |

`git commit` 始终是本地操作，不需要 GitHub Token。`fork_token` 只发布已经提交的对象。

如果同一个 Classic PAT 能完成两个职责，需要把同一个值明确写入两个字段：

```toml
[github]
fork_token = "<同一个 Classic PAT>"
pull_request_token = "<同一个 Classic PAT>"
```

两个字段之间不做隐式共享。

### 公共仓库 PAT

普通公共跨 owner fork 最简单的方案是一个 **Token (classic)**，只选择：

```text
[x] public_repo
```

把它写入默认配置的两个字段，或者对应项目覆盖的两个字段。

如果使用 Fine-grained PAT：

- `fork_token`：选择个人 fork，授予 **Contents: Read and write**。Metadata read 自动包含。
- `pull_request_token`：选择社区 upstream，授予 **Pull requests: Read and write**。Metadata read 自动包含。

Fine-grained PAT 绑定一个 resource owner。成为另一个个人账号仓库的管理员或协作者，并不一定能在 Token 的 resource owner 中选择该账号。

### 私有仓库 PAT

私有 fork 与 upstream 分属不同 resource owner 时，推荐一个受控的 **Token (classic)**，选择：

```text
[x] repo
```

该 PAT 所属用户必须能读取两个私有仓库、更新个人 fork，并向 upstream 创建 PR。在需要时完成组织审批、SAML SSO 授权和 IP allow list 要求。

创建 Token 时，应登录拥有个人 fork 的账号。进入 GitHub 的 **Settings > Developer settings > Personal access tokens > Tokens (classic) > Generate new token (classic)**，选择 `repo`、设置有效期；如果 upstream 组织启用了 SAML SSO，还要通过 **Configure SSO** 授权该组织。组织也可能要求管理员批准 Token，批准前访问私有仓库会失败。

公共项目继续使用较小权限的默认凭证，私有凭证放在项目覆盖中。例如 remotes 是 `liuppx/billing` 和 `yeying-community/billing`：

```toml
[github.projects.billing]
fork_token = "<liuppx 账号具有 repo scope 的 Classic PAT>"
pull_request_token = "<同一枚 liuppx Classic PAT>"
```

项目 key 是 `billing`，因为 upstream 仓库是 `yeying-community/billing`。不要增加 `origin`、`upstream`、`visibility` 或 `provider`。同一个 PAT 明确填写两次是有意设计：`fork_token` 更新个人 fork，`pull_request_token` 读取两个私有仓库并创建 upstream PR；实现不会在两个字段之间隐式共享凭证。

把两枚 Fine-grained PAT 按 owner 拆开，通常不足以完成私有跨 owner PR。某枚 Token 即使可以管理 upstream PR，只要它看不到私有 head fork，就可能成功查询 upstream PR，却在比较或创建 `fork-owner:main -> upstream-owner:main` 时失败。

如果两个仓库属于同一个 resource owner，也可以使用同时选择两端仓库、具有 Contents read/write 和 Pull requests read/write 的 Fine-grained PAT。

只有提交确实修改 `.github/workflows/` 时才额外选择：

```text
[x] workflow
```

不要申请无关的企业、组织、包、Hook、用户、密钥或仓库管理权限。

### 私有 Fork 访问检查

配置私有项目后，在第一次交付前从目标仓库运行只读检查：

```bash
python3 /path/to/yeying-github/scripts/github_access_check.py
```

命令会读取实际的 `origin` 和 `upstream` remotes，按 upstream 仓库名选择项目配置，并验证：

- `origin` 是真正的 GitHub fork，且 parent 正是当前 upstream。
- API 模式凭证可以写入个人 fork。
- PR 凭证可以读取两个私有仓库。
- PR 凭证可以比较 `upstream/main...fork-owner:main`。

准备完成时，输出结尾应为：

```text
fork publish access: verified
pull request repository access: verified
private head comparison: verified (ahead=<n>, behind=<n>)
access check: ready
```

对于私有仓库，HTTP 404 通常表示当前凭证看不到仓库，并不一定表示仓库不存在。如果 upstream 可以访问，但 origin 或 compare 返回 404，应改用一枚属于 fork owner、具有 `repo` scope 的 Classic PAT，或者使用同时安装在两端 owner 上的 GitHub App。

### GitHub App

全局 GitHub App 配置：

```toml
[github.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

登录并保存全局 App user token：

```bash
python3 scripts/github_app_login.py --project default
```

项目独立 GitHub App 配置：

```toml
[github.projects.internal-service]

[github.projects.internal-service.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

登录并保存该项目的 App token：

```bash
python3 scripts/github_app_login.py --project internal-service
```

App 需要 **Metadata: Read**、**Contents: Read and write**、**Pull requests: Read and write**，并安装到 fork 和 upstream 两边。授权用户本身也必须访问两端仓库。Skill 会把 `user_token`、`refresh_token` 和 `expires_at` 写入选中的 App 配置表，并在需要时自动刷新。

### API 与 Git 模式

API 模式使用 `fork_token` 和 `pull_request_token`，适合 `git push`、SSH 或 `gh` 被限制的环境：

```toml
[github]
mode = "api"
```

Git 模式通过 `scripts/sync.sh` 使用 SSH Key 或 HTTPS credential helper 执行 fetch/push。`fork_token` 可以为空，`pull_request_token` 供 `scripts/pr.sh` 或 `gh` 使用：

```toml
[github]
mode = "git"
```

### 配置优先级

配置文件：

1. `--config /绝对路径/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

传输模式：

1. `--mode`
2. `YEYING_GITHUB_MODE`
3. 匹配的 `[github.projects.<repository>]`
4. `[github]`
5. 默认值：`api`

认证：

1. 匹配项目中声明了任一认证字段时，使用完整的项目认证
2. 否则使用 `[github]` 的完整认证

### 安全与运行

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

包含任一 Token 的配置文件必须是 `0600` 或更严格。Skill 不读取环境中的 `GH_TOKEN`、`GITHUB_TOKEN` 或 `UPSTREAM_TOKEN` 作为配置，不打印 Token，不强推、不合并 PR，也不修改仓库可见性、分支保护或协作者。

先运行 dry-run：

```bash
python3 scripts/github_delivery.py --dry-run \
  --title "chore(scope): accurately describe the delivery"
```
