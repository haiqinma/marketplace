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
origin_token = ""
upstream_token = ""

[github.private]
provider = "pat"
origin_token = ""
upstream_token = ""
```

两个 profile 完全隔离：

- 公共交付只读取 `[github.public]`。
- 私有交付只读取 `[github.private]`。
- 自动检测为公共时，不读取私有 Token。
- 自动检测无法匿名读取两端时，才加载私有 provider。
- 旧版 `[github].origin_token`、`[github].upstream_token` 仅兼容映射到公共 profile，不得用于私有交付。

## Provider

每个 profile 的 `provider` 可以是：

- `pat`：使用 profile 内的 `origin_token` 和 `upstream_token`。
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

公共 API 模式：

- public `origin_token`：个人 fork 的 Metadata read、Contents read/write。
- public `upstream_token`：社区仓库 Metadata read、Pull requests read/write。

私有 API 模式：

- private `origin_token`：私有 fork 的 Metadata read、Contents read/write。
- private `upstream_token`：必须读取私有 origin 和 upstream，并在 upstream 拥有 Pull requests read/write。
- 跨 resource owner 的私有 PR 推荐使用具有 `repo` scope 的受控 classic PAT，或者 GitHub App user access token。

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
