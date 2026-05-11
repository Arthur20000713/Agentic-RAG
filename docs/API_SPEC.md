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

当前 API 进度：

- `POST /api/chat`：调用 Agent workflow，返回 `intent`、`answer`、`sources`、`tools_used`。
- `POST /api/documents/upload`：保存上传文件并创建 RAG ingestion task；不解析文档。
- `GET /api/tasks/{task_id}`：查询 ingestion task。
- `POST /api/tasks/{task_id}/index`：同步代理到 RAG-SERVER CLI ingestion，未配置真实路径时返回明确失败。
- `POST /api/measurement/analyze`：调用体尺分析服务并返回结构化报告。
