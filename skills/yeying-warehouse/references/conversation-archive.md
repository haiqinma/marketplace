# 对象归档示例

调用方需要保存一组相互关联的原始资料时，可以在同一目录生成三个对象：

```text
/personal/reviews/conversations/<conversationId>/transcript.md
/personal/reviews/conversations/<conversationId>/transcript.json
/personal/reviews/conversations/<conversationId>/manifest.json
```

- `transcript.md`：人工阅读视图，内容由调用方定义。
- `transcript.json`：结构化原始资料，内容由调用方定义。
- `manifest.json`：记录来源、采集时间、导出范围、完整性、脱敏状态，以及前两个文件的 SHA-256。

使用 `warehouse.object.put` 逐个写入，默认 `overwrite=false`。路径应包含稳定的 conversationId；若用户明确要求修订已归档内容，先读取当前 ETag，再以 `overwrite=true` 和 `ifMatch=<etag>` 条件覆盖。每个调用传同一 `traceId`，便于关联三次写入。

Markdown 只是阅读视图，不能单独宣称为完整或不可篡改的审计证据。调用方无法取得原始资料时，应在 manifest 中明确标记 `complete=false` 和缺失项。

写入前由调用方移除访问令牌、密码、私钥、密钥文件正文和其他不应持久化的秘密。Warehouse 不解析或替调用方判断对象正文是否含敏感信息，也不会把凭证写入对象。
