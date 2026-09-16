# Warehouse Tool 契约模板

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

一个 Warehouse Tool 只有同时满足以下条件才可接入 MCP 或 Agent：

1. Warehouse API 已稳定，且 Warehouse 本身执行最终权限校验。
2. 请求能关联用户或受控服务身份、授权范围和有效期。
3. 输入、输出、错误、超时、重试和副作用都能被机器判断。
4. 调用和业务变更可以通过 `requestId` / `traceId` 审计。
5. 相关文档和测试已同步更新。
