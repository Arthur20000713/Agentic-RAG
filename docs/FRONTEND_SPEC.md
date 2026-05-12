# Frontend Spec

V2.3 前端使用 FastAPI 静态文件，不引入 Node、React、Vite 或构建步骤。

## 入口

- 静态目录：`backend/app/static/frontend/`
- 访问路径：`/app`
- 文件：`index.html`、`app.js`、`styles.css`

## 页面

- Chat：提交 `/api/chat`，展示 answer、intent、risk_level 和 follow_up_questions。
- Measurement：提交 `/api/measurement/analyze`，展示 report 和 evidence。
- Debug JSON：展示最近一次 API 响应的原始 JSON。

## 约束

- 不实现完整文档管理后台。
- 不改变后端统一响应 envelope。
- 不静默伪造引用、工具结果或 trace。
- 引用和工具摘要必须来自 API 返回数据。
