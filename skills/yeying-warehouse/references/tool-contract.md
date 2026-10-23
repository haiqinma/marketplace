# Warehouse 通用 Tool 契约模板

使用本模板评审或新增 Warehouse Tool。模板只描述语义契约；实际 URL、认证方式和 schema 必须引用 Warehouse 的正式 API 文档。

## 基本信息

```yaml
name: warehouse.object.stat
version: "1.0"
description: 获取调用方有权访问的对象元数据
owner: Warehouse
sourceApi:
  method: GET
  path: /api/v1/public/assets/object
```

## HTTP Tool 认证

当前调用方式是：

```http
Authorization: Bearer <Warehouse 登录 JWT>
```

生产 Skill 客户端从以下环境变量读取配置：

```text
YEYING_WAREHOUSE_URL
YEYING_WAREHOUSE_TOOL_TOKEN
```

交互式本地验证可以临时使用 `YEYING_WAREHOUSE_TOKEN`。客户端优先读取 `YEYING_WAREHOUSE_TOOL_TOKEN`。

`YEYING_WAREHOUSE_TOKEN` 不是 WebDAV AK/SK、S3 AK/SK，也不是其他系统的内部凭证。Warehouse 会在每次请求中重新执行用户、路径、UCAN、配额和对象条件校验。凭证不得出现在 Tool 参数、归档正文或日志中。

生产调用方应使用 Warehouse 创建的短期 scoped Tool credential，通过同一个 Bearer 位置发送；用户 JWT 仅用于交互式本地验证。

凭证轮换使用 `POST /api/v1/public/tools/credentials/{id}/rotate`，旧 secret 会立即失效且新 secret 只返回一次。审计查询使用 `GET /api/v1/public/tools/audits`；响应不包含 secret、secret hash 或对象正文。

## 请求与响应

```yaml
input:
  type: object
  required: [path]
  properties:
    path:
      type: string
      pattern: "^/(personal|apps|services)(/.*)?$"
output:
  type: object
  required: [path, size, etag, checksumSha256, modifiedAt]
  properties:
    path: {type: string}
    size: {type: integer, format: int64}
    contentType: {type: string}
    etag: {type: string}
    checksumSha256: {type: string}
    modifiedAt: {type: string, format: date-time}
```

## 安全和执行语义

```yaml
requiredScopes: [asset:read]
resourceScope: path
sideEffects: none
confirmationRequired: false
idempotency: safe
timeout: 10s
retry:
  retryableErrors: [RATE_LIMITED, STORAGE_UNAVAILABLE]
  maxAttempts: 2
audit:
  fields: [requestId, traceId, subject, owner, path, result, latencyMs]
```

写操作必须额外写清楚：

- `Idempotency-Key` 或业务幂等键。
- `If-Match` / `If-None-Match` 等并发条件。
- 是否需要用户确认或审批。
- 部分成功和重复请求的结果。
- 失败后的回滚或人工处理方式。

## 评审结果

一个 Warehouse Tool 只有同时满足以下条件才可供外部调用方接入：

1. Warehouse API 已稳定，且 Warehouse 本身执行最终权限校验。
2. 请求能关联用户或受控服务身份、授权范围和有效期。
3. 输入、输出、错误、超时、重试和副作用都能被机器判断。
4. 调用和业务变更可以通过 `requestId` / `traceId` 审计。
5. 相关文档和测试已同步更新。

## 直接写入

`warehouse.object.put` 可由已授权调用方直接调用，不要求逐次人工确认。默认只创建对象；同路径同内容的重试返回成功，不同内容返回 `OBJECT_EXISTS`。覆盖已有对象必须显式传 `overwrite=true`，需要并发保护时传 `ifMatch`。

```yaml
name: warehouse.object.put
version: "1.0"
requiredScopes: [asset:write]
sideEffects: write
confirmationRequired: false
idempotency: idempotent
maxDecodedBytes: 5242880
encodings: [utf-8, base64]
```

直接调用不代表无限权限：Warehouse 必须校验调用身份、授权路径、UCAN app scope、配额和 checksum，并在审计日志中记录 requestId、traceId、主体、路径、大小、checksum 和覆盖标记，不记录正文。
