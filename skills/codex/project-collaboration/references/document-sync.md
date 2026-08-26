# 文档同步配置

`project_docs_sync.py` 使用 UTF-8 JSON 配置文件。配置只描述源文件和 Project 目标，不保存 AK/SK。

```json
{
  "project_root_id": 0,
  "files": [
    {
      "source": "/workspace/books/yeying/社区产品架构.md",
      "target": "社区基线/社区产品架构.md"
    },
    {
      "source": "/workspace/project/docs/项目管理架构V3.md",
      "target": "Project/项目管理架构V3.md",
      "target_file_id": 456
    }
  ]
}
```

字段说明：

- `project_root_id`：Project 文件柜中的根目录 ID，根目录为 `0`。
- `files[].source`：本地 UTF-8 Markdown 文件路径。
- `files[].target`：相对于 `project_root_id` 的目标路径，父目录必须已存在。
- `files[].target_file_id`：可选，已知目标文件 ID 时优先使用，避免重名误匹配。

执行建议：

```bash
python3 scripts/project_docs_sync.py check --config docs-sync.json
python3 scripts/project_docs_sync.py plan --config docs-sync.json
python3 scripts/project_docs_sync.py apply --config docs-sync.json --state .project-docs.state.json
```

`.project-docs.state.json` 可能包含环境相关的文件 ID，不应提交到公共仓库。同步前应确保目标父目录已经通过 `file-add --type folder` 创建；第一阶段同步器不会自动创建缺失的中间目录。
