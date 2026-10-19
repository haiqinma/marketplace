# 夜莺 GitHub 交付 / YeYing GitHub Delivery

## 中文

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

### 配置与安全

默认配置文件是 `~/.yeying/skills/github/config.toml`。`origin_token` 用于个人 fork，`upstream_token` 用于社区 PR。包含 Token 的配置文件必须是 `0600` 或更严格权限。Skill 不从 `GH_TOKEN`、`GITHUB_TOKEN` 或 `UPSTREAM_TOKEN` 读取配置，也不会执行强制推送、合并 PR 或修改分支保护。

## English

### Purpose

`yeying-github` implements the YeYing community fork delivery flow: develop on the contributor fork's `main` branch, publish to `origin/main`, and then reuse or create a pull request into the community `upstream/main` branch.

### Transport Modes

- `api`: recreate and publish local commits through the GitHub API when `git push`, SSH, or GitHub CLI is restricted.
- `git`: prefer the target repository's existing `scripts/sync.sh` and `scripts/pr.sh`.

Entry point:

```bash
python3 scripts/github_delivery.py \
  --title "feat(scope): accurately describe the complete delivery"
```

### Configuration and Safety

The default configuration file is `~/.yeying/skills/github/config.toml`. `origin_token` accesses the personal fork and `upstream_token` manages the community pull request. A configuration file containing tokens must use mode `0600` or stricter. The Skill does not read configuration from `GH_TOKEN`, `GITHUB_TOKEN`, or `UPSTREAM_TOKEN`, and it does not force-push, merge pull requests, or change branch protection.
