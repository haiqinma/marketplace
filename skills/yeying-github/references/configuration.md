# 配置与执行规则

## 设计原则

凭证按账号默认值或具体仓库对组织，不按 public/private 组织。公共或私有只是 GitHub 仓库元数据，不应决定从哪个凭证 profile 取值。

配置只有两层：

- `[github]`：所有仓库的默认配置。
- `[github.projects.<name>]`：精确匹配 origin 和 upstream 的可选项目覆盖。

## 默认配置

```toml
[github]
mode = "api"
visibility = "auto"
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"
fork_token = ""
pull_request_token = ""
```

`[github]` 只允许：

```text
mode
visibility
sync_script
pr_script
fork_token
pull_request_token
github_app
projects
```

不支持 `provider`、共享 `token`、`origin_token`、`upstream_token`、`public` 或 `private` 子 profile。未知字段触发 `ConfigError`。

## 项目覆盖

```toml
[github.projects.marketplace]
origin = "liuppx/marketplace"
upstream = "yeying-community/marketplace"
visibility = "public"
```

项目名称只允许字母、数字、`_` 和 `-`。每个项目必须配置：

```text
origin = "owner/repository"
upstream = "owner/repository"
```

匹配规则：

1. 从当前 Git remote 解析 origin 和 upstream。
2. 两端都匹配时选择该项目，仓库名比较不区分大小写。
3. 只有一端匹配时停止，避免静默使用默认配置。
4. 两个项目不得声明相同的仓库对。
5. 没有任何相关匹配时使用 `[github]`。

项目表允许覆盖：

```text
mode
visibility
sync_script
pr_script
fork_token
pull_request_token
github_app
```

## 继承规则

普通字段逐项继承：

```text
CLI -> 环境变量 -> 项目 -> 全局 -> 内置默认值
```

认证不逐项拼接：

1. 项目没有任何认证字段时，完整继承全局认证。
2. 项目声明 `fork_token`、`pull_request_token` 或 `github_app` 中任一项时，完整替换全局认证。
3. 项目缺少的 Token 保持缺失，并由对应执行路径给出准确错误。

例如，下面的项目不会继承全局 `pull_request_token`：

```toml
[github]
fork_token = "<global-fork>"
pull_request_token = "<global-pr>"

[github.projects.special]
origin = "me/special"
upstream = "org/special"
fork_token = "<project-fork>"
```

项目 `special` 的 `pull_request_token` 为空。这样可以防止两个权限域的凭证被意外组合。

## 认证方式推断

对最终选中的默认或项目认证执行：

1. 非空 `fork_token` 或 `pull_request_token` 表示 PAT。
2. 存在对应的 `github_app` 子表表示 GitHub App。
3. 非空 PAT 与 GitHub App 同时存在时触发 `ConfigError`。
4. 两者都没有时内部按 PAT 处理，让具体操作报告缺少哪个字段。

全局 App 表：

```toml
[github.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

项目 App 表：

```toml
[github.projects.private_repo]
origin = "me/private-repo"
upstream = "org/private-repo"
visibility = "private"

[github.projects.private_repo.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

登录命令：

```bash
python3 scripts/github_app_login.py --project default
python3 scripts/github_app_login.py --project private_repo
```

登录和刷新会把 `user_token`、`refresh_token`、`expires_at` 原子写回实际提供认证的 App 表。如果项目继承全局 App，使用 `--project <name>` 最终仍会更新 `[github.github_app]`。

## 可见性

### 自动探测

`visibility = "auto"` 时：

1. 先解析项目配置和认证。
2. 使用最终的 `pull_request_token` 或 GitHub App user token 请求 origin 元数据。
3. 使用同一凭证请求 upstream 元数据。
4. 读取 `visibility`，旧响应以 `private` 布尔字段回退。
5. 两端可见性不同则停止。

每次执行固定增加两次已认证 REST API 请求。Token 本身不会被消耗，但请求计入 GitHub API rate limit。普通用户 Token 通常是每小时 5000 次；实际额度以 GitHub 响应和账号策略为准。

不再先匿名请求。匿名请求常见额度是每出口 IP 每小时 60 次，HTTP 403 既可能是额度耗尽，也可能是策略限制，不能可靠推断仓库为私有。

### 显式配置

`visibility = "public"` 或 `"private"` 时，Skill 信任配置并跳过上述两次专门的元数据请求。

显式配置不改变凭证选择，也不会跳过 API 发布和 PR 管理所需的正常请求。建议把显式可见性放在对应项目表中，而不是作为所有项目的全局断言。

## PAT 职责

| 字段 | API 模式 | Git 模式 |
| --- | --- | --- |
| `fork_token` | 上传本地已提交对象并更新个人 `origin/main` | 不使用，Git 使用 SSH 或 HTTPS credential helper |
| `pull_request_token` | 自动探测可见性，并读取元数据、查询、创建或更新 upstream PR | 临时映射为 `GH_TOKEN` 传给 `pr.sh`/`gh` |

API 模式要求两个字段。Git 模式允许 `fork_token` 为空，但要求 `pull_request_token`。

同一个 PAT 覆盖两个职责时，两个字段填写同一个值；实现不做隐式共享。

## PAT 权限

公共跨 owner fork 的 Classic PAT：

```text
public_repo
```

私有跨 owner fork 的 Classic PAT：

```text
repo
```

修改 `.github/workflows/` 时按需增加：

```text
workflow
```

Fine-grained PAT：

- `fork_token`：个人 fork 的 Metadata read、Contents read/write。
- `pull_request_token`：社区 upstream 的 Metadata read、Pull requests read/write。
- 自动探测或私有交付时，PR 凭证必须读取 origin 和 upstream。
- Fine-grained PAT 绑定一个 resource owner，跨 owner 私有 fork 可能无法由一个 Token 覆盖。

## GitHub App 边界

- User access token 权限是用户权限、App 权限和 installation 仓库范围的交集。
- App 必须安装到 fork 和 upstream 两边，授权用户也必须访问两端。
- App 需要 Metadata read、Contents read/write 和 Pull requests read/write。
- Device Flow 适合本地 Agent 环境。
- Installation token 只属于一个 installation 且一小时过期，不作为跨 owner PR 的默认组合凭证。

## Git 模式

- `sync.sh` 不接收 PAT 或 GitHub App Token；fetch/push 使用 SSH Key 或 HTTPS credential helper。
- `pr.sh`/`gh` 只接收最终解析出的 `pull_request_token`，临时映射为 `GH_TOKEN`。
- Git 模式不支持 `--allow-dirty`。

## 安全规则

- 配置文件包含任一 Token 时必须是 `0600` 或更严格。
- 不在日志、错误、命令参数、PR 正文或提交中显示 Token。
- 不把环境中的 `GH_TOKEN`、`GITHUB_TOKEN` 或 `UPSTREAM_TOKEN` 作为配置来源。
- 不自动修改组织 PAT 策略、SSO、App installation、私有 fork 策略或仓库可见性。
- 不强推、不合并 PR、不修改分支保护或协作者。
