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
2. `[github.projects.<name>]` 是可选的，只在当前仓库的 origin 和 upstream 都匹配时生效。

不再按公共仓库和私有仓库拆分凭证 profile。仓库可见性是仓库元数据，凭证属于默认账号配置或某个具体项目。

### 最小默认配置

没有匹配到项目覆盖时，所有仓库都使用下面的配置：

```toml
[github]
mode = "api"                  # api | git
visibility = "auto"           # auto | public | private
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

只有某个仓库对需要不同配置时，才增加项目条目：

```toml
[github.projects.marketplace]
origin = "liuppx/marketplace"
upstream = "yeying-community/marketplace"
visibility = "public"
```

`marketplace` 是本地配置名称，可以包含字母、数字、`_` 和 `-`。

当前 Git remote 必须同时匹配下面两个字段，匹配时不区分大小写：

```text
origin   -> liuppx/marketplace
upstream -> yeying-community/marketplace
```

如果只有一端匹配，交付会直接停止并报告配置错误，不会静默回退到默认凭证。这样可以避免复制配置或拼写错误导致凭证用错项目。

上面的例子继承默认传输模式、脚本和凭证，但明确指定仓库是公共的，因此不需要额外执行可见性探测。

### 项目独立凭证

项目可以完整替换默认认证：

```toml
[github.projects.internal_service]
origin = "liuppx/internal-service"
upstream = "example-org/internal-service"
mode = "api"
visibility = "private"
fork_token = "<写入个人私有 fork 的 PAT>"
pull_request_token = "<读取两端私有仓库并创建 PR 的 PAT>"
```

认证按整体继承：

- 项目没有配置 `fork_token`、`pull_request_token` 或 `github_app` 时，完整继承全局认证。
- 项目只要声明任一认证字段，就只使用项目认证。
- 不会把项目的 `fork_token` 与全局的 `pull_request_token` 混合，也不会反向混合。
- 项目需要为所选传输模式完整配置它需要的所有凭证。

这条规则可以让凭证归属和权限错误保持明确。

### 可见性探测与 Token 消耗

默认配置：

```toml
[github]
visibility = "auto"
```

Skill 会先选择匹配的项目配置；没有匹配时使用全局默认配置。然后解析该配置中的 PAT 或 GitHub App 凭证，并发送：

```text
GET /repos/<origin-owner>/<origin-repository>
GET /repos/<upstream-owner>/<upstream-repository>
```

两次请求都会使用已选中的 `pull_request_token`，或者 GitHub App user token。代码优先读取响应中的 `visibility` 字段，并以 `private` 布尔字段作为兼容回退。origin 和 upstream 必须返回相同的可见性。

每次交付会因此消耗两次已认证 REST API 请求额度。Token 不会像一次性凭证一样被“消耗”或缩短寿命；消耗的是 GitHub API rate limit。普通已认证用户请求通常为每小时 5000 次，但 GitHub 账号、组织、企业和 App 策略可能改变实际额度。

Skill 不再执行匿名探测。GitHub 匿名 API 通常按出口 IP 共享每小时 60 次额度；匿名额度耗尽可能返回 HTTP 403。旧设计会把这个 403 当成“可能是私有仓库”，这正是公共 Marketplace 仓库此前被误判并切换到 private profile 的原因。

如果希望跳过这两次专门的元数据请求，可以明确配置可见性，推荐放在具体项目中：

```toml
[github.projects.marketplace]
origin = "liuppx/marketplace"
upstream = "yeying-community/marketplace"
visibility = "public"
```

```toml
[github.projects.internal_service]
origin = "liuppx/internal-service"
upstream = "example-org/internal-service"
visibility = "private"
```

显式可见性会被当作可信配置，不再额外探测。但 API 发布和 PR 操作仍然会发送正常的 GitHub API 请求，所以这不会让 API 模式变成“无需 Token”。

### 两个 Token 字段的职责

| 字段 | API 模式 | Git 模式 | 权限要求 |
| --- | --- | --- | --- |
| `fork_token` | 发布本地已经存在的 commit/tree/blob，并更新个人 `origin/main` | 不使用 | 个人 fork 的 Metadata read、Contents read/write |
| `pull_request_token` | `auto` 时探测可见性；读取元数据并查询、创建或更新 upstream PR | 临时传给 `pr.sh`/`gh` | upstream 的 Metadata read、Pull requests read/write；私有交付时必须读取两端仓库 |

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

如果两个仓库属于同一个 resource owner，也可以使用同时选择两端仓库、具有 Contents read/write 和 Pull requests read/write 的 Fine-grained PAT。

只有提交确实修改 `.github/workflows/` 时才额外选择：

```text
[x] workflow
```

不要申请无关的企业、组织、包、Hook、用户、密钥或仓库管理权限。

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
[github.projects.internal_service]
origin = "liuppx/internal-service"
upstream = "example-org/internal-service"
visibility = "private"

[github.projects.internal_service.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

登录并保存该项目的 App token：

```bash
python3 scripts/github_app_login.py --project internal_service
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

传输模式和可见性：

1. `--mode` / `--visibility`
2. `YEYING_GITHUB_MODE` / `YEYING_GITHUB_VISIBILITY`
3. 匹配的 `[github.projects.<name>]`
4. `[github]`
5. 默认值：`api` 和 `auto`

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
