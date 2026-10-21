# 配置与执行规则

## 设计原则

凭证按账号默认值或具体项目组织，不按 public/private 组织。仓库可见性不改变凭证选择和交付算法，因此不需要配置或预先探测。

配置只有两层：

- `[github]`：所有仓库的默认配置。
- `[github.projects.<repository>]`：按当前 upstream 仓库名自动选择的可选项目覆盖。

## 默认配置

```toml
[github]
mode = "api"
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"
fork_token = ""
pull_request_token = ""
```

`[github]` 只允许：

```text
mode
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
mode = "git"
```

项目 key 必须等于 upstream Git remote 中的仓库名，匹配时不区分大小写。项目名称只允许字母、数字、`_` 和 `-`。

```text
Git remote upstream -> git@github.com:yeying-community/marketplace.git
项目 key = marketplace
```

匹配规则：

1. 从当前 Git remote 解析真实 origin 和 upstream，remote 是仓库关系和 PR 路由的唯一来源。
2. 从 upstream 的 `owner/repository` 提取 `repository`。
3. 使用仓库名匹配 `[github.projects.<repository>]`，比较不区分大小写。
4. 没有匹配项目时使用 `[github]`。
5. `origin` 和 `upstream` 不允许出现在项目配置中，避免与 Git remote 形成两套事实来源。

不同 upstream owner 下的同名仓库会选择同一个项目 key。如果它们需要不同凭证，使用不同配置文件，并通过 `--config` 或 `YEYING_GITHUB_CONFIG` 选择。

项目表允许覆盖：

```text
mode
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
[github.projects.private-repo]

[github.projects.private-repo.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
```

登录命令：

```bash
python3 scripts/github_app_login.py --project default
python3 scripts/github_app_login.py --project private-repo
```

登录和刷新会把 `user_token`、`refresh_token`、`expires_at` 原子写回实际提供认证的 App 表。如果项目继承全局 App，使用 `--project <name>` 最终仍会更新 `[github.github_app]`。

## 仓库访问与 API 配额

Skill 不发送专门用于判断 public/private 的元数据请求。实际操作直接验证访问权限：

1. API 发布使用 `fork_token` 读取并更新个人 fork。
2. PR 查询、创建和更新使用 `pull_request_token` 访问 upstream。
3. GitHub App user token 同时承担两个职责。

Token 本身不会被消耗，但实际 API 请求计入 GitHub rate limit。普通用户 Token 通常是每小时 5000 次；实际额度以 GitHub 响应和账号策略为准。

## PAT 职责

| 字段 | API 模式 | Git 模式 |
| --- | --- | --- |
| `fork_token` | 上传本地已提交对象并更新个人 `origin/main` | 不使用，Git 使用 SSH 或 HTTPS credential helper |
| `pull_request_token` | 读取所需仓库和 PR 数据，并查询、创建或更新 upstream PR | 临时映射为 `GH_TOKEN` 传给 `pr.sh`/`gh` |

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

推荐由个人 fork owner 创建该 Token，并在项目表的两个字段中明确填写同一个值：

```toml
[github.projects.billing]
fork_token = "<fork owner Classic PAT with repo scope>"
pull_request_token = "<the same Classic PAT>"
```

Token owner 必须访问两端私有仓库。组织启用 SAML SSO 时需要执行 Configure SSO；组织启用 PAT 审批时需要等待批准。两枚分别绑定不同 resource owner 的 Fine-grained PAT，可能形成“fork_token 只能看 origin、pull_request_token 只能看 upstream”的断裂权限，无法比较私有 head 或创建跨仓库 PR。

首次私有交付前运行：

```bash
python3 scripts/github_access_check.py
```

该检查显式验证 fork parent、个人 fork 写权限、PR Token 对两端仓库的读取权限，以及 `base...fork-owner:head` compare。它不会打印 Token，也不会修改 GitHub 状态。

修改 `.github/workflows/` 时按需增加：

```text
workflow
```

Fine-grained PAT：

- `fork_token`：个人 fork 的 Metadata read、Contents read/write。
- `pull_request_token`：社区 upstream 的 Metadata read、Pull requests read/write。
- 私有交付时，PR 凭证必须具备创建跨仓库 PR 所需的访问权限。
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
