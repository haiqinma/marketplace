# 认证配置与执行规则

## 配置结构

`[github]` 只保存传输和脚本设置。认证信息分别存放在 `[github.public]` 与 `[github.private]`：

```toml
[github]
mode = "api"
visibility = "auto"
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"

[github.public]
provider = "pat"
token = ""             # 可选：origin 和 upstream 共用
origin_token = ""
upstream_token = ""

[github.private]
provider = "pat"
token = ""             # 可选：origin 和 upstream 共用
origin_token = ""
upstream_token = ""
```

两个 profile 完全隔离：

- 公共交付只读取 `[github.public]`。
- 私有交付只读取 `[github.private]`。
- 自动检测为公共时，不读取私有 Token。
- 自动检测无法匿名读取两端时，才加载私有 provider。
- 旧版 `[github].origin_token`、`[github].upstream_token` 仅兼容映射到公共 profile，不得用于私有交付。

同一个 profile 内的 PAT 解析顺序：

1. `origin_token` 或 `upstream_token` 存在时，该角色使用专用值。
2. 角色专用值不存在时，该角色回退到 `token`。
3. `token` 不会跨 public/private profile 回退。

字段名代表 remote 角色，不代表本地 Git 操作：

| 字段 | API 模式 | Git 模式 |
| --- | --- | --- |
| `token` | 作为两个角色的共享后备凭证 | 只可能用于 `pr.sh`/`gh`，不参与 Git push |
| `origin_token` | 上传本地已经创建的对象并更新个人 `origin/main` | 不使用 |
| `upstream_token` | 读取仓库并查询、创建或更新社区 upstream PR | 临时映射为 `GH_TOKEN` 传给 `pr.sh`/`gh` |

`git commit` 始终是本地操作，不需要 GitHub Token。

## Provider

每个 profile 的 `provider` 可以是：

- `pat`：使用 profile 内的共享 `token`，或角色专用的 `origin_token` 和 `upstream_token`。
- `github_app`：使用 `[github.<visibility>.github_app]` 中通过 Device Flow 取得的 user access token。一个用户令牌同时用于 origin 和 upstream。

GitHub App 配置：

```toml
[github.private]
provider = "github_app"

[github.private.github_app]
client_id = "Iv1.xxxxxxxxxxxxxxxx"
user_token = ""       # 由 github_app_login.py 写入
refresh_token = ""    # 由 github_app_login.py 写入
expires_at = ""       # Unix 时间戳字符串，由脚本写入
```

运行登录：

```bash
python3 scripts/github_app_login.py --visibility private
```

用户令牌距过期不足五分钟时，交付脚本使用 refresh token 自动刷新并原子写回配置。通过 Device Flow 获取的 refresh token 在刷新时不需要 Client Secret。配置文件包含任一 Token 时必须是 `0600` 或更严格。

## 可见性解析

`visibility = "auto"` 的流程：

1. 不带认证读取 origin 和 upstream 元数据。
2. 两端都可读且都为 public 时，选择公共 profile。
3. 任一端无法匿名读取时，选择私有 profile，并使用其 upstream 凭证重新读取两端。
4. 两端实际可见性不同、显式配置与实际状态不符，或者凭证看不到任一私有仓库时停止。

显式 `public` 或 `private` 会跳过 profile 猜测，但仍读取 GitHub 元数据验证断言。

## PAT 权限

### Fine-grained PAT

Fine-grained PAT 绑定一个 resource owner。另一个个人账号仓库的管理员或协作者权限，不等于可以把那个个人账号选为 Token 的 resource owner。

Fine-grained PAT 适合 `origin_token`：

- public `origin_token`：个人 fork 的 Metadata read、Contents read/write。
- public `upstream_token`：只有贡献者能选择社区组织作为 resource owner 且组织批准 Token 时，才使用社区仓库 Metadata read、Pull requests read/write 的 fine-grained PAT。

普通外部贡献者通常不能为另一个个人账号或不可选的社区组织创建 upstream fine-grained PAT。公共跨 owner fork 推荐把只有 `public_repo` scope 的 classic PAT 写入 `[github.public].token`。

私有 origin 和 upstream 属于同一个 resource owner 时，可以创建一个同时选择两个仓库的 fine-grained PAT，授予 Contents read/write 与 Pull requests read/write，并写入 `[github.private].token`。

私有 origin 和 upstream 分属不同 resource owner 时，一个 fine-grained PAT 通常无法覆盖两端。把同一个值复制到 `origin_token` 和 `upstream_token` 不会改变 Token 的 resource owner 或仓库范围。

### Classic PAT

跨 resource owner 的公共或私有 PR 可以使用 classic PAT：

- 两端都为公共仓库时，只选择 `public_repo`，写入 `[github.public].token`。
- 任一端为私有仓库时，选择顶层 `repo`，写入 `[github.private].token`。
- GitHub 自动选中 `repo` 的子 scope 属于正常行为。
- 仅当提交会修改 `.github/workflows/` 时额外选择 `workflow`。
- 不选择 `admin:enterprise`、`write:network_configurations`、`admin:org`、`delete_repo`、packages、hooks、user、audit log、codespaces、Copilot、projects 或密钥管理 scope。
- PAT 用户必须读取目标仓库、更新个人 fork，并能在 upstream 创建 PR；私有交付时还必须读取两端私有仓库。
- Token 应设置较短有效期、保存在 `0600` 文件中并定期轮换。

组织可能禁用 classic PAT，或要求 PAT 审批、SAML SSO 授权、IP allow list。失败时不得尝试扩大权限或更改组织策略，应向用户报告具体的 HTTP 状态和配置要求。

## GitHub App 边界

Skill 使用 user-to-server Token，而不是 installation access token：

- User access token 的权限是“用户权限、App 权限、App installation 仓库范围”三者的交集。
- App 必须安装在 fork 和 upstream 两边，用户也必须访问两边。
- Device Flow 适合 Codex、Claude 和其他本地无回调服务器的 CLI 环境。
- Installation token 只属于一个 installation 且一小时过期。它适合服务端自动化，但无法自然合并两个 owner 的私有仓库权限，因此不是本 Skill 跨 owner PR 的默认方案。

## Git 模式

Git 模式继续优先使用仓库的 `scripts/sync.sh` 和 `scripts/pr.sh`：

- `sync.sh` 不继承 PAT 或 GitHub App Token。Git push/fetch 使用 SSH key 或 HTTPS credential helper。
- `pr.sh`/`gh` 子进程只接收当前已选 profile 的 upstream 凭证，并临时映射为 `GH_TOKEN`。
- 公共和私有 profile 不会同时注入。
- Git 模式不支持 `--allow-dirty`。

## 安全规则

- 不在日志、错误、命令参数、PR 正文或提交中显示 Token。
- 不使用环境中的 `GH_TOKEN`、`GITHUB_TOKEN`、`UPSTREAM_TOKEN` 作为配置来源。
- 不自动修改组织 PAT 策略、SSO、App installation、私有 fork 策略或仓库可见性。
- 不把 GitHub App client secret 或 PEM 私钥作为跨 owner PR 的替代捷径。
