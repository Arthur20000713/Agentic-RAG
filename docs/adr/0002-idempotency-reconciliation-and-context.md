# ADR-0002：幂等、执行对账与会话版本

- 状态：Accepted
- 日期：2026-07-29
- 适用阶段：V7 P1-P7

## 背景

chat 是有模型成本且结果不完全确定的 POST。网络超时不能证明 Python 未执行；盲目重试可能重复调用模型并生成不同答案。Java还必须避免同一会话并发 turn 覆盖问诊上下文。

## 决策

### Java 业务幂等

- 写请求要求 `Idempotency-Key`；
- Java以 `(owner_id, operation_id)` 建唯一约束；
- 相同 key 与相同 payload 返回已有业务结果；
- 相同 key 与不同 payload 返回 409；
- chat POST 默认不自动重试。

### Python 短期执行日志

Python在执行前按 `operation_id + request_hash` 创建 `ai_execution_record`，并在返回前持久化最终响应。记录位于 Python运维卷，有过期和清理策略，不是会话或任务事实源。

Java收到不确定结果时将任务置为 `SUBMIT_UNKNOWN`，通过 `GET /internal/v1/ai/runs/{operationId}` 对账：

- 已完成：写入唯一助手消息并完成任务；
- 仍运行：继续有限轮询；
- 不存在且超过安全窗口：标记失败；
- 同 operation 不同 hash：409。

模型提供方层面的 exactly-once 无法在进程崩溃时保证。系统只承诺一个 operation 最多接受一个业务结果，不在简历中宣称模型调用 exactly-once。

### 会话版本

- MySQL `conversation.context_version` 是唯一权威；
- `active_operation_id` 保证同一会话一次只有一个 turn；
- Redis context 必须携带与 MySQL相同的版本；
- 缓存缺失或落后时，Python从有限历史和空 context 重建；
- Java持久化消息和新版本后再更新 Redis；
- 崩溃遗留 operation 由对账任务修复或释放。

## 后果

收益：

- 不会因 HTTP超时重复写消息；
- 并发 turn 不会覆盖会话状态；
- Redis只是缓存，丢失不影响耐久事实。

代价：

- Python需要技术执行表和查询接口；
- Java需要对账任务；
- 极端崩溃下可能浪费一次模型调用成本。

## 不采用

- 对所有 POST 自动 retry；
- 只用易失 Redis实现 chat 幂等；
- 使用全局分布式锁；
- 为第一版引入 Kafka 或事务消息。
