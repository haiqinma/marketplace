# Project Automation API

## Authentication

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

Sort GET query parameters by name and encode with RFC 3986 rules. Hash the exact JSON request bytes for POST. Derive the HMAC key as the lowercase hexadecimal `SHA-256(Secret Key)` string, then calculate a lowercase hexadecimal HMAC-SHA256 signature. Timestamps have a five-minute window and nonces cannot be reused within that window.

## Endpoints

| Command | Method and path | Access boundary |
| --- | --- | --- |
| `projects` | `GET /api/project/lists` | 项目范围 |
| `tasks` | `GET /api/project/task/lists` | 项目范围 |
| `task` | `GET /api/project/task/one` 等 | 项目范围 |
| `comment` | `POST /api/dialog/msg/sendtext` | 项目范围；传入 `--update-id` 时编辑当前用户的指定消息 |
| `update` | `POST /api/project/task/update` | 项目范围 |
| `status` | `POST /api/project/task/update` | 项目范围 |
| `file-info` | `GET /api/project/task/filedetail` | 项目范围 |
| `download` | `GET /api/project/task/filedown` | 项目范围 |

The server treats the token as its owner's signed authentication method and reuses the same business permissions as the Web API. It additionally verifies token project bindings, current project membership, active user state, and task visibility. Non-project high-risk APIs such as user, organization, system, license, and token management are unavailable to AK/SK.

`update` and `status` use the standard task update contract. Task `content` is Project rich-text HTML; the bundled client converts Markdown supplied with `--content` or `--content-file` before sending it. Use `--content-format html` only for content already produced by the Project editor. The server applies the same task, workflow, and project permissions as the Web API. The file download endpoint returns binary data rather than the JSON envelope; the bundled client writes it directly to the requested output path.

## Response

Successful responses use:

```json
{"ret": 1, "msg": "success", "data": {}}
```

Any response where `ret` is not `1` is a failed operation. Authentication failures intentionally do not reveal whether the AK, timestamp, nonce, or signature caused the rejection.
