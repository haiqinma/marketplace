# Project Automation API

## Authentication

The signed client accepts environment variables or a local TOML file. The precedence is command-line `--config`, `YEYING_PROJECT_CONFIG`, then `~/.yeying/skills/project/config.toml`. The file uses a `[project]` section with `url`, `access_key`, and `secret_key`; `YEYING_PROJECT_URL`, `YEYING_PROJECT_AK`, and `YEYING_PROJECT_SK` override file values when set. A file containing `secret_key` must be mode `0600` or stricter.

Every request sends `X-YY-AK`, `X-YY-Timestamp`, `X-YY-Nonce`, and `X-YY-Signature`.
The canonical string is:

```text
METHOD
PATH
QUERY_STRING
BODY_SHA256
TIMESTAMP
NONCE
```

Sort GET query parameters by name and encode with RFC 3986 rules. Array parameters use PHP-style bracket notation (`key[0]=val&key[1]=val`). Hash the exact JSON request bytes for POST (JSON body) or the empty-string hash for multipart uploads (Swoole parses multipart before the signature layer, so the server sees an empty body). Derive the HMAC key as the lowercase hexadecimal `SHA-256(Secret Key)` string, then calculate a lowercase hexadecimal HMAC-SHA256 signature. Timestamps have a five-minute window and nonces cannot be reused within that window.

## Task Endpoints

| Command | Method and path | Access boundary |
| --- | --- | --- |
| `projects` | `GET /api/project/lists` | 项目范围 |
| `tasks` | `GET /api/project/task/lists` | 项目范围 |
| `task-create` | `POST /api/project/task/add` | 项目范围；需要任务创建权限 |
| `task` | `GET /api/project/task/one` 等 | 项目范围 |
| task dialog | `GET /api/project/task/dialog` | 项目范围；创建或获取任务聊天室 |
| `comment` | `POST /api/dialog/msg/sendtext` | 项目范围；`--model` 或 `YEYING_AGENT_MODEL` 作为 `model_name`；传入 `--update-id` 时编辑当前用户的指定消息 |
| `update` | `POST /api/project/task/update` | 项目范围 |
| `status` | `POST /api/project/task/update` | 项目范围 |
| `file-info` | `GET /api/project/task/filedetail` | 项目范围 |
| `download` | `GET /api/project/task/filedown` | 项目范围 |

The server treats the token as its owner's signed authentication method and reuses the same business permissions as the Web API. It additionally verifies token project bindings, current project membership, active user state, and task visibility.

`model_name` is provenance metadata for the task discussion. Send only the real active model ID exposed by the host; never infer it from `source_tool`. When the host does not expose a model, omit `model_name` and retain `model_missing_reason` in the execution archive. Internal deployment aliases should follow the same redaction and Project access boundary as other execution metadata.

## File Cabinet Endpoints

| Command | Method and path | Access boundary |
| --- | --- | --- |
| `file-lists` | `GET /api/file/lists` | 用户范围（令牌持有者的文件和共享文件） |
| `file-one` | `GET /api/file/one` | 用户范围；`with_text=yes` 提取文本内容 |
| `file-add` | `GET /api/file/add` | 用户范围；创建文件夹或文档 |
| `file-save` | `POST /api/file/content/save` | 用户范围；保存 Markdown/文本文档内容 |
| `file-read` | `GET /api/file/content` | 用户范围；读取文档内容 |
| `file-upload` | `POST /api/file/content/upload` | 用户范围；multipart 上传 |
| `file-search` | `GET /api/file/search` | 用户范围；按文件名搜索 |
| `file-link` | `GET /api/file/link` | 用户范围；生成/刷新分享链接 |
| `file-remove` | `GET /api/file/remove` | 用户范围；`ids` 为数组 |
| `file-move` | `GET /api/file/move` | 用户范围；`ids` 为数组 |
| execution archive upload | `POST /api/dialog/msg/sendfile` | 任务对话附件；`dialog_id` 必须是目标任务的对话 ID |

File cabinet endpoints require the Project token `file_cabinet` permission scope. File cabinet authorization is then userid-scoped: the token can access files owned by the token user, files created by the token user, and files shared to the token user. Requests without a specific `id` parameter (listing, searching, root-level creation) are authorized by the scope gate first and then by the controller layer through `User::auth()` and `File::permissionFind`.

任务评论、生命周期记录发布和执行归档发布前都会调用 `project/task/dialog` 创建或获取目标任务聊天室；如果任务尚无 `dialog_id`，Project 会在该请求中创建并回写。随后执行归档使用目标任务的 `dialog_id` 调用 `dialog/msg/sendfile`。Project 会把任务对话中的非图片文件登记到任务附件，随后可通过 `project/task/files`、`project/task/filedown` 读取和校验。该路径与用户文件柜是不同的授权边界。

Chunked upload endpoints under `/api/upload/*` are only authorized for `scene=file_cabinet` sessions when called with AK/SK. The `file_cabinet` scope does not authorize `image`, `generic_file`, or `dialog_file` upload scenes.

### Multipart upload signing

For `file-upload`, the client sends query parameters (`pid`, `cover`) in the URL and the file binary as a multipart body. Because Swoole parses multipart before the signature middleware runs, `$request->getContent()` returns an empty string. The client signs with `sha256("")` as the body hash to match.

### File content save format

For Markdown documents (`type=document`), the `content` parameter is a JSON string:

```json
{"type": "md", "content": "# Heading\n\nBody text."}
```

For code/text files (`type=txt` or `type=code`):

```json
{"type": "txt", "content": "plain text content"}
```

### File content read format

`file-read` returns the file content as JSON:

```json
{"content": {"type": "md", "content": "# Heading\n\nBody text."}}
```

## Response

Successful responses use:

```json
{"ret": 1, "msg": "success", "data": {}}
```

Any response where `ret` is not `1` is a failed operation. Authentication failures intentionally do not reveal whether the AK, timestamp, nonce, or signature caused the rejection.
