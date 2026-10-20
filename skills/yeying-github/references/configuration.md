# 认证配置与执行规则

## 配置结构

`[github]` 只保存传输、可见性和仓库脚本设置。PAT 必须放在对应的公共或私有 profile 中：

```toml
[github]
mode = "api"
visibility = "auto"
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"

[github.public]
provider = "pat"
fork_token = ""
pull_request_token = ""

[github.private]
provider = "pat"
fork_token = ""
pull_request_token = ""
```

PAT profile 只允许：

```text
provider
fork_token
pull_request_token
github_app
```

不存在共享 `token` 或字段回退。凭证不得放在 `[github]` 根表。所有未知字段都会触发 `ConfigError`，不会被静默忽略。

两个 profile 完全隔离：

- 公共交付只读取 `[github.public]`。
- 私有交付只读取 `[github.private]`。
- 自动检测为公共时，不加载私有凭证。
- 自动检测无法匿名读取两端时，使用私有 `pull_request_token` 验证两端。

## PAT 职责

| 字段 | API 模式 | Git 模式 |
| --- | --- | --- |
| `fork_token` | 上传本地已提交对象并更新个人 `origin/main` | 不使用，Git 使用 SSH 或 HTTPS credential helper |
| `pull_request_token` | 读取仓库元数据并查询、创建或更新 upstream PR | 临时映射为 `GH_TOKEN` 传给 `pr.sh`/`gh` |

API 模式要求两个字段。Git 模式允许 `fork_token` 为空，但仍要求 `pull_request_token`。

同一个 PAT 覆盖两个职责时，两个字段填写同一个值。实现不做隐式共享，以便错误信息和权限审计始终指向具体职责。

## Provider

每个 profile 的 `provider` 可以是：

- `pat`：使用 `fork_token` 和 `pull_request_token`。
- `github_app`：通过 Device Flow 获取一个 user access token，运行时把它同时映射为 fork 与 PR 凭证。

GitHub App 配置：

```toml
[github.private]
provider = "github_app"

[github.private.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
user_token = ""       # github_app_login.py 写入
refresh_token = ""    # github_app_login.py 写入
expires_at = ""       # Unix 时间戳字符串
```

登录命令：

```bash
python3 scripts/github_app_login.py --visibility private
```

用户令牌距过期不足五分钟时，Skill 使用 refresh token 自动刷新并原子写回配置。Device Flow 的 refresh token 刷新不需要 Client Secret。

## 可见性解析

`visibility = "auto"`：

1. 不带认证读取 origin 和 upstream 元数据。
2. 两端都可读且为 public 时选择公共 profile。
3. 任一端无法匿名读取时选择私有 profile，使用其 `pull_request_token` 重新读取两端。
4. 两端实际可见性不同、显式断言不匹配，或凭证看不到任一私有仓库时停止。

显式 `public` 或 `private` 只决定预期 profile，仍会读取 GitHub 元数据验证。

## 公共 PAT 权限

Classic PAT：

```toml
[github.public]
provider = "pat"
fork_token = "<public_repo PAT>"
pull_request_token = "<同一个 public_repo PAT>"
```

- 只选择 `public_repo`。
- 修改 `.github/workflows/` 时额外选择 `workflow`。
- PAT 用户必须能更新个人 fork，并能从该 fork 创建 upstream PR。

Fine-grained PAT：

- `fork_token`：个人 fork 的 Metadata read、Contents read/write。
- `pull_request_token`：社区 upstream 的 Metadata read、Pull requests read/write。
- Fine-grained PAT 绑定一个 resource owner；只有贡献者能选择社区组织且 Token 获得批准时，第二个配置才可行。

## 私有 PAT 权限

跨 resource owner 推荐 Classic PAT：

```toml
[github.private]
provider = "pat"
fork_token = "<repo PAT>"
pull_request_token = "<同一个 repo PAT>"
```

- 选择顶层 `repo`。
- PAT 用户必须读取两端私有仓库、更新个人 fork并创建 upstream PR。
- 组织可能要求 PAT 审批、SAML SSO 授权或 IP allow list。
- 私有 fork network 必须得到组织、企业和仓库策略允许。

两个私有仓库属于同一个 resource owner 时，可以使用同时选择两端仓库、具有 Contents read/write 与 Pull requests read/write 的 Fine-grained PAT。

## Classic PAT 禁止的额外权限

除按需增加 `workflow` 外，不选择以下无关 scope：

```text
admin:enterprise
write:network_configurations
admin:org
delete_repo
packages
hooks
user
audit log
codespaces
Copilot
projects
GPG/SSH signing key administration
```

## GitHub App 边界

- User access token 的权限是用户权限、App 权限和 installation 仓库范围的交集。
- App 必须安装到 fork 和 upstream 两边，授权用户也必须访问两端。
- App 需要 Metadata read、Contents read/write 和 Pull requests read/write。
- Device Flow 适合本地 Agent 环境。
- Installation token 只属于一个 installation 且一小时过期，不作为跨 owner 私有 PR 的默认凭证。

## Git 模式

- `sync.sh` 不接收 PAT 或 GitHub App Token；fetch/push 使用 SSH Key 或 HTTPS credential helper。
- `pr.sh`/`gh` 只接收 `pull_request_token`，临时映射为 `GH_TOKEN`。
- 公共和私有 profile 不会同时注入。
- Git 模式不支持 `--allow-dirty`。

## 安全规则

- 配置文件包含任一 Token 时必须是 `0600` 或更严格。
- 不在日志、错误、命令参数、PR 正文或提交中显示 Token。
- 不把环境中的 `GH_TOKEN`、`GITHUB_TOKEN` 或 `UPSTREAM_TOKEN` 作为配置来源。
- 不自动修改组织 PAT 策略、SSO、App installation、私有 fork 策略或仓库可见性。
- 不强推、不合并 PR、不修改分支保护或协作者。
