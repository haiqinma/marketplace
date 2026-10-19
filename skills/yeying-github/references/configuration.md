# 配置与凭证

`yeying-github` 使用一个明确的传输模式开关。解析优先级为：

1. `--mode api|git`
2. `YEYING_GITHUB_MODE`
3. 配置文件 `[github].mode`
4. 默认 `api`

配置文件解析顺序为：

1. `--config /path/to/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

示例：

```toml
[github]
mode = "api"
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"
origin_token = "用于个人 fork 的 Token"
upstream_token = "用于社区 PR 的 Token"
```

`sync_script` 和 `pr_script` 相对当前目标仓库根目录解析。Git 模式优先使用这些仓库自带脚本，以保留各项目已经验证过的 rebase、push、认证和 PR 处理逻辑。

Token 只从本配置文件读取，不回退到 `GH_TOKEN`、`GITHUB_TOKEN` 或 `UPSTREAM_TOKEN`。配置文件包含任一 Token 时，必须限制为当前用户可读写：

```bash
chmod 600 ~/.yeying/skills/github/config.toml
```

## API 模式

- `origin_token`：读取和更新个人 `origin/main`。
- `upstream_token`：查询、创建或更新社区仓库 PR。
- API 模式不会执行 `git push` 或依赖 SSH 传输，但仍需要本地 `git` 读取 commit、tree、remote 和工作区状态。
- 创建私有 fork 到私有 upstream 的 PR 时，执行 PR 操作的一个 Token 必须同时读取 head 和 base，并拥有 upstream Pull requests 写权限。
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
