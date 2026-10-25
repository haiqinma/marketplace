# 夜莺项目协作

[English](README.md)

### 用途

`yeying-project` 通过 AK/SK 签名 API 管理夜莺产品研发任务的完整生命周期，包括任务接收、分析、方案审批、实现、验证、GitHub 交付和审计归档。

### 核心能力

- 创建、读取和更新 Project 任务及评论。
- 将本地工作区绑定到明确的 Project 任务。
- 使用带任务 ID 后缀的本地文件隔离并行任务。
- 记录分析、审批、文档、验证、提交和 PR 结果。
- 归档 Codex、Claude 或其他 Agent 可公开获得的执行历史和真实模型信息。
- 管理 Project 文件柜并发布经过审阅的本地文档。

### 配置

默认配置文件是 `~/.yeying/skills/project/config.toml`：

```toml
[project]
url = "https://project.example.com"
access_key = "yyak_..."
secret_key = "<只显示一次的 Secret Key>"

[tester]
path = "../tester" # 可选；相对当前产品项目根目录
```

配置文件选择优先级从高到低为：

1. `--config /绝对路径/project.toml`
2. `YEYING_PROJECT_CONFIG`
3. `~/.yeying/skills/project/config.toml`

如果设置了 `YEYING_PROJECT_URL`、`YEYING_PROJECT_AK` 和 `YEYING_PROJECT_SK`，它们会覆盖 TOML 中对应字段。长期本地 Agent 使用应优先选择受保护的 TOML 或认可的 Secret Manager，不建议把凭证写进 shell 启动文件。

字段说明：

- `url`：Project 服务根地址，不包含 API 路径后缀。从浏览器打开的 Project 地址或部署管理员处获取。
- `access_key`：Project 自动化访问令牌的 Access Key。
- `secret_key`：与 Access Key 匹配的 Secret Key，仅在创建或轮换时显示一次。
- `[tester].path`：共享 `tester` 测试库的路径，可选；相对路径以当前产品项目根目录解析。未配置时默认使用同级目录 `<产品项目父目录>/tester`。该规则适用于社区所有项目。

`tester` 是社区共享的 Playwright/Chromium E2E 测试库。跨项目用户流程和 E2E 用例必须放在 `tester`，不得新建在产品项目仓库中；产品内部单元测试仍可留在产品自己的原生测试套件。Project API 客户端只读取 `[project]`，`[tester]` 由 Agent 工作流程使用。

#### 获取 Project AK/SK

1. 使用 Agent 需要代表的 Project 用户登录。
2. 打开右上角头像菜单，进入 **设置 → 访问令牌**，也可以直接访问 `/manage/setting/automation-token`。
3. 点击 **创建令牌**，填写易于识别的名称，并至少选择一个当前用户已经加入的项目。
4. 只有需要调用文件柜命令时才勾选 **文件柜** scope。任务讨论附件和执行归档属于所选项目的任务能力，不需要额外文件柜 scope。
5. 选择界面提供的 7、30 或 90 天有效期，创建后立即保存 Access Key 和 Secret Key。关闭弹窗后无法找回 Secret Key，丢失时必须轮换。

令牌以创建者身份访问所选项目，不会绕过项目成员关系、任务可见性、用户状态或文件共享权限。不同自动化任务需要不同项目或 scope 边界时，应分别创建令牌。

保护本地配置：

```bash
mkdir -p ~/.yeying/skills/project
chmod 700 ~/.yeying/skills/project
chmod 600 ~/.yeying/skills/project/config.toml
```

执行任何写操作前先验证只读访问：

```bash
python3 scripts/project_api.py projects
```

`.project-task-<task-id>.json`、`.project-lifecycle-<task-id>.json` 和 `.project-execution-<task-id>.json` 等文件是任务绑定和生命周期状态，不是凭证文件。它们不得包含 AK/SK，也不应提交到 Git。

### 边界

AK/SK 不得进入仓库、任务评论、执行归档或最终回复。隐藏提示、隐藏推理和宿主未暴露的工具输出不得声称已被捕获。未经可追溯的方案批准，不应开始实现；验证、PR 和执行归档不完整时，不应把任务标记为完成。协议细节见 [`references/api.md`](references/api.md)。
