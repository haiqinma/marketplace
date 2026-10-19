# 夜莺 GitHub 交付

[English](README.md)

### 用途

`yeying-github` 用于夜莺社区的 fork 交付流程：在贡献者个人仓库的 `main` 分支开发，发布到 `origin/main`，然后复用或创建指向社区 `upstream/main` 的 Pull Request。

### 传输模式

- `api`：通过 GitHub API 重建并发布本地提交，适合 `git push`、SSH 或 GitHub CLI 受限的环境。
- `git`：优先复用目标仓库的 `scripts/sync.sh` 和 `scripts/pr.sh`。

运行入口：

```bash
python3 scripts/github_delivery.py \
  --title "feat(scope): 准确描述完整交付内容"
```

### 配置

默认配置文件是 `~/.yeying/skills/github/config.toml`：

```toml
[github]
mode = "api"
sync_script = "scripts/sync.sh"
pr_script = "scripts/pr.sh"
origin_token = "<个人 fork 使用的 Token>"
upstream_token = "<社区 PR 使用的 Token>"
```

配置文件选择优先级从高到低为：

1. `--config /绝对路径/config.toml`
2. `YEYING_GITHUB_CONFIG`
3. `~/.yeying/skills/github/config.toml`

传输模式选择优先级从高到低为：

1. `--mode api|git`
2. `YEYING_GITHUB_MODE`
3. `[github].mode`
4. 默认 `api`

字段说明：

- `mode`：`api` 通过 GitHub API 发布提交；`git` 使用仓库现有 Git/gh 脚本。
- `sync_script`：Git 模式使用的仓库相对路径或绝对路径同步脚本，默认 `scripts/sync.sh`。
- `pr_script`：Git 模式使用的仓库相对路径或绝对路径 PR 脚本，默认 `scripts/pr.sh`。
- `origin_token`：API 模式下读取个人 fork 并更新 `origin/main`。
- `upstream_token`：读取 PR 的 head/base 仓库，并在社区 upstream 查询、创建或更新 PR。

#### 获取 GitHub Token

进入 GitHub **Settings → Developer settings → Personal access tokens**，创建 fine-grained Token；如果私有跨所有者 PR 无法由绑定单一资源所有者的 fine-grained Token 覆盖，则使用经过控制的 classic Token 或 GitHub App 凭证。

- origin 凭证需要访问贡献者 fork，并拥有仓库 Contents 读写权限。
- upstream 凭证需要读取 PR 两端引用，并拥有社区仓库 Pull requests 读写权限。
- 两个私有仓库属于不同账号或组织时，绑定单一资源所有者的 fine-grained Token 可能无法同时读取两端。应使用一个经过批准、能读取两个仓库并管理 upstream PR 的凭证。
- 仓库范围和有效期应尽量收窄；交付环境变化后及时撤销或轮换。

GitHub 新建 PAT 后通常只显示一次明文。应直接保存到受保护的本地配置文件，不要粘贴到 shell 历史、Issue、PR 正文或仓库文件。

```bash
mkdir -p ~/.yeying/skills/github
chmod 700 ~/.yeying/skills/github
chmod 600 ~/.yeying/skills/github/config.toml
```

Skill 明确忽略环境中的 `GH_TOKEN`、`GITHUB_TOKEN` 和 `UPSTREAM_TOKEN`，它们不是配置来源。Git 模式仅为兼容现有 `gh`/`pr.sh`，可能在子进程内部把配置的 `upstream_token` 临时注入为 `GH_TOKEN`。

可先执行只读验证，不产生远程写入：

```bash
python3 scripts/github_delivery.py --mode api --dry-run \
  --title "docs(scope): 准确描述完整交付内容"
```

### 安全边界

Skill 不会强制推送、合并 PR、修改分支保护、添加协作者或修改仓库可见性。任何输出都不得显示 Token。更多细节见 [`references/configuration.md`](references/configuration.md)。
