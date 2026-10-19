# 配置、仓库可见性与凭证

`yeying-github` 将“怎么传输”和“仓库是什么访问模型”作为两个独立配置。推荐使用 `mode = "api"`、`visibility = "auto"`，除非环境明确允许 Git/gh，或需要用显式可见性阻止误配置。

传输模式解析优先级为：

1. `--mode api|git`
2. `YEYING_GITHUB_MODE`
3. 配置文件 `[github].mode`
4. 默认 `api`

仓库可见性解析优先级为：

1. `--visibility auto|public|private`
2. `YEYING_GITHUB_VISIBILITY`
3. 配置文件 `[github].visibility`
4. 默认 `auto`

配置文件解析顺序为：

1. `--config /path/to/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

示例：

```toml
[github]
mode = "api"
visibility = "auto"
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"
origin_token = "用于个人 fork 的 Token"
upstream_token = "用于社区 PR 的 Token"
```

`visibility` 的含义：

- `auto`：推荐。通过 GitHub API 分别读取 `origin` 和 `upstream` 元数据，自动识别为 `public` 或 `private`，并在执行前输出最终结果。
- `public`：断言两端都是公共仓库。如果 GitHub 返回私有仓库，立即停止。
- `private`：断言两端都是私有仓库。如果 GitHub 返回公共仓库，立即停止。

`origin` 和 `upstream` 必须具有相同可见性。公共与私有仓库混合时会停止，因为本 Skill 支持的是同一 GitHub fork network 内的 `main -> main` PR，而不是任意两个仓库之间的内容复制。

## 选择矩阵

| 仓库 | API 模式 | Git 模式 |
| --- | --- | --- |
| 公共 | `origin_token` 用 API 更新个人 fork；`upstream_token` 读取两端并管理社区 PR | Git/SSH/HTTPS 更新个人 fork；公共 upstream 可匿名 fetch；`upstream_token` 用于 `pr.sh`/`gh` 管理 PR |
| 私有 | `origin_token` 必须读取并更新私有 fork；`upstream_token` 必须读取两个私有仓库并管理 upstream PR | Git/SSH/HTTPS 凭证必须访问两个私有 remote；`upstream_token` 还必须读取两端并管理 upstream PR |

选择方式：

- 运行环境限制 `git push`、SSH 或 `gh` 时，选择 `mode = "api"`。
- 仓库已经有可靠的 `scripts/sync.sh`、`scripts/pr.sh`，且 Git/SSH/gh 可用时，选择 `mode = "git"`。
- 大多数用户保持 `visibility = "auto"`。只有希望配置与远端状态不一致时立即失败，才显式选择 `public` 或 `private`。
- 两种传输都会执行相同的远端可见性预检；`--dry-run` 也会执行该只读检查。

`sync_script` 和 `pr_script` 相对当前目标仓库根目录解析。Git 模式优先使用这些仓库自带脚本，以保留各项目已经验证过的 rebase、push、认证和 PR 处理逻辑。

Token 只从本配置文件读取，不回退到 `GH_TOKEN`、`GITHUB_TOKEN` 或 `UPSTREAM_TOKEN`。配置文件包含任一 Token 时，必须限制为当前用户可读写：

```bash
chmod 600 ~/.yeying/skills/github/config.toml
```

## API 模式

- `origin_token`：读取和更新个人 `origin/main`。
- `upstream_token`：查询、创建或更新社区仓库 PR。
- API 模式不会执行 `git push` 或依赖 SSH 传输，但仍需要本地 `git` 读取 commit、tree、remote 和工作区状态。
- 公共仓库的 `origin_token` 可限制到个人 fork，至少授予 Metadata 读取和 Contents 读写权限。
- 公共仓库的 `upstream_token` 至少需要读取社区仓库和 Pull requests 读写权限；公共 fork 元数据可读，但仍会使用该 Token 完成统一预检。
- 创建私有 fork 到私有 upstream 的 PR 时，`upstream_token` 必须同时读取 head 和 base，并拥有 upstream Pull requests 写权限。
- 私有仓库如果启用了组织 SAML SSO、IP allow list 或 PAT 审批，Token 还必须经过相应授权；否则 GitHub 可能返回 `403` 或为隐藏私有仓库返回 `404`。
- 不要把 Token 写入仓库、日志、命令参数或 PR 内容。

## Git 模式

Git 模式优先使用目标仓库中的：

```text
scripts/sync.sh
scripts/pr.sh
```

执行同步时必须存在 `sync.sh`，除非调用方显式使用 `--skip-sync`。如果仓库尚未提供 `pr.sh`，包装器会退化为使用已安装且已认证的 `gh pr list/create/edit`，仍会复用开放 PR 并校正标题。

包装器使用以下环境变量调用它们：

```text
AUTO_PUSH=true
INTERACTIVE=false
AUTO_FILL_PR=false
PR_TITLE=<显式标题>
PR_BODY=<生成或传入的正文>
```

`pr.sh` 通常依赖 `gh`。包装器会清除调用环境中的 Token，并仅在 `pr.sh`/`gh` 子进程中把配置的 `upstream_token` 作为 `GH_TOKEN` 注入；该环境变量只是兼容现有工具的进程内传输方式，不是配置来源。同步脚本不会继承任何 GitHub Token。Git 模式不支持 `--allow-dirty`，因为 `sync.sh` 可能执行 fetch、rebase 和 push。

Git remote 的认证独立于 TOML 中的 Token：

- 公共仓库：upstream fetch 通常不需要认证；origin push 仍需 SSH key 或 HTTPS credential helper。
- 私有仓库：origin 和 upstream 的 fetch/push 都必须由 SSH key、HTTPS credential helper 或仓库脚本支持的 Git 凭证完成。
- `origin_token` 不会注入 Git 同步脚本。不要假定在 TOML 中设置它就能让 `git push` 获得认证。
- `upstream_token` 仅为可见性预检和 `pr.sh`/`gh` PR 操作提供认证，不替代 Git remote 的 SSH/HTTPS 凭证。

## Token 来源与权限

进入 GitHub **Settings -> Developer settings -> Personal access tokens** 创建 fine-grained PAT；如果私有跨所有者 PR 无法由单一 resource owner 的 fine-grained PAT 覆盖，则使用经过组织批准和严格控制的 classic PAT 或 GitHub App 凭证。

- `origin_token`：API 模式使用。选择个人 fork，授予 Metadata 读取、Contents 读写。私有 fork 还需要该 Token 被允许访问对应私有仓库。
- `upstream_token`：两种模式都使用。选择社区 upstream，授予 Metadata 读取、Pull requests 读写；私有 PR 还必须让同一个凭证读取私有 origin。若 GitHub 的 fine-grained PAT 无法跨两个 resource owner，可使用组织认可的其他凭证方案。
- Classic PAT 对公共仓库通常使用 `public_repo`，私有仓库通常需要 `repo`；同时遵守组织 SSO、审批和有效期策略。

GitHub 新建 PAT 后通常只显示一次明文。将值直接写入受保护的本地配置，不要出现在 shell 历史、Issue、PR、日志或仓库文件中。
