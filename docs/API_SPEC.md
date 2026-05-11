# API 契约初稿

当前项目 API 层统一返回：

```json
{
  "code": 0,
  "message": "success",
  "data": {},
  "request_id": "req_xxx"
}
```

错误码以 `backend/app/core/errors.py` 为准。所有接口必须保留 `code`、`message`、`data`、`request_id` 四个字段。

V1 默认不直接实现 RAG 检索逻辑，所有知识库查询必须经过 `RagServerClient`。

应用层答案拼装规则：

- 引用只能来自 `RagSearchResult.citations`。
- RAG 为空、低置信或失败时，不展示伪造来源。
- RAG 失败时必须明确说明无法基于检索结果给出结论。
