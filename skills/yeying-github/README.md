# YeYing GitHub Delivery

[简体中文](README_CN.md)

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
