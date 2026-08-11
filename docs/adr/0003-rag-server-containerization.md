# ADR-0003：RAG-SERVER 固定版本与容器化

- 状态：Proposed，存在外部仓库阻断
- 日期：2026-07-29
- 适用阶段：V7 P0、P2、P6

## 背景

当前 FastAPI 通过 MCP stdio 调用 sibling `RAG-SERVER`。运行配置包含本机绝对路径，本地验收还可能选择 `.tmp_tests` 中的运行时副本。该状态无法从干净 clone 复现，也不能直接用于 Docker Compose。

## 决策

优先方案：

1. 在 RAG-SERVER 自身仓库形成无密钥、干净且远端可达的提交；
2. 将该提交作为 Git submodule 或固定构建制品加入主项目；
3. Python镜像内安装主项目与固定 RAG-SERVER；
4. FastAPI进程复用一个 MCP stdio 子进程；
5. Chroma、BM25、图片索引和模型缓存使用持久卷；
6. 知识库源文件和 manifest 必须来自可追踪制品，不引用宿主绝对路径；
7. readiness 必须实际验证 MCP tools/list 和目标 collection；
8. FastAPI lifespan 负责启动、stderr drain 和 shutdown 回收。

如果同镜像依赖冲突或 MCP 子进程生命周期无法稳定管理，则把 RAG-SERVER 拆成第五个内部服务。不能为了维持“四服务”而隐藏不可复现依赖。

## 安全要求

- 不复制现有配置中的任何 inline key；
- 现有真实 key 按已暴露处理并轮换；
- 镜像不包含 `.env`、API key、模型权重或运行数据；
- `.env.example` 只包含占位符；
- Python和 RAG-SERVER 默认不发布宿主端口。

## P0 退出条件

- 固定 commit/制品可从干净环境获取；
- Docker build 不读取 sibling dirty worktree；
- 容器内 MCP tools/list 成功；
- 目标 collection 可被 readiness 发现；
- 重启后索引仍在且没有失控子进程；
- 无 Windows 绝对路径和明文 secret。

在外部 RAG-SERVER 仓库完成上述安全清理前，本 ADR 保持 Proposed，P1 可开发契约，但不得声称真实 RAG Compose 已完成。
