# ADR-0001：Java 业务服务与 Python AI 服务边界

- 状态：Accepted
- 日期：2026-07-29
- 适用阶段：V7 P0-P7

## 背景

现有 FastAPI 同时承担 AI 编排、会话、任务、业务数据和技术 trace。客户端通过请求体 `user_id` 或 `X-Client-ID` 标识所有者，无法提供可信认证和资源级授权。新增 Java 层后如果继续让两侧共同写业务数据，会形成双事实源。

## 决策

调用方向固定为：

`客户端 -> Spring Boot -> FastAPI -> RAG-SERVER / 模型`

Spring Boot 是唯一对外入口，负责：

- 用户、登录、JWT、角色和权限；
- 会话、消息和资源所有权；
- 业务任务、文档元数据和审计；
- 农场、动物和体尺主数据；
- Java-Python 调用治理。

FastAPI 是内部 AI 执行服务，负责：

- RAG、引用和 RAG-SERVER MCP；
- LangGraph/Agent、问诊、工具和模型；
- 低置信度、Verifier、Safety 和 fallback；
- AI 技术 trace 和评测。

MySQL 是业务事实源。Python不直连 Java MySQL，不验证用户 JWT，不保存耐久会话、消息或业务任务。

## 上下文

MySQL `conversation.context_version` 是唯一版本权威。Java在 Redis保存 Python定义、Java不解释的 opaque AI context，并在每次调用中同时传递有限历史。Python无状态返回 `nextContext` 和下一版本。

## 兼容

迁移期保留旧 `/api` 用于回归。目标 Compose profile 禁用旧 chat、conversation、task 和 document 写接口，并只初始化 Python AI 运维表。

## 后果

收益：

- 用户权限和业务事务只有一个权威；
- AI 代码继续复用；
- Redis丢失时可以从 MySQL历史安全重建；
- Java和 Python可独立测试和部署。

代价：

- 需要新的 `/internal/v1` 契约；
- 需要停机迁移，不能双写；
- Python现有 `SessionContextService` 必须改为请求内上下文计算。

## 不采用

- 将每个 Java 模块拆成独立微服务；
- Python和 Java共享业务表；
- Python解析用户 JWT；
- 第一版引入 MQ、分布式事务或服务网格。
