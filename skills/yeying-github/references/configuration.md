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
```

`sync_script` 和 `pr_script` 相对当前目标仓库根目录解析。Git 模式优先使用这些仓库自带脚本，以保留各项目已经验证过的 rebase、push、认证和 PR 处理逻辑。

## API 模式

```bash
export GH_TOKEN="personal-fork-token"
export UPSTREAM_TOKEN="upstream-pr-token"
```

- `GH_TOKEN` 或 `GITHUB_TOKEN`：读取和更新个人 `origin/main`。
- `UPSTREAM_TOKEN`：查询、创建或更新社区仓库 PR；未设置时回退到 `GH_TOKEN`/`GITHUB_TOKEN`。
- API 模式不会执行 `git push` 或依赖 SSH 传输，但仍需要本地 `git` 读取 commit、tree、remote 和工作区状态。
- 创建私有 fork 到私有 upstream 的 PR 时，执行 PR 操作的一个 Token 必须同时读取 head 和 base，并拥有 upstream Pull requests 写权限。
- 不要把 Token 写入本配置文件、仓库或 PR 内容。

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

`pr.sh` 通常依赖 `gh`。认证可以来自 `GH_TOKEN`，也可以来自脚本支持的 `gh auth login`。Git 模式不支持 `--allow-dirty`，因为 `sync.sh` 可能执行 fetch、rebase 和 push。
