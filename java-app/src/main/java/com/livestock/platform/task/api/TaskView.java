package com.livestock.platform.task.api;

import com.livestock.platform.task.domain.BizTask;
import com.livestock.platform.task.domain.TaskStatus;
import com.livestock.platform.task.domain.TaskType;
import java.time.Instant;

public record TaskView(
        String id,
        String ownerId,
        String conversationId,
        TaskType type,
        String operationId,
        TaskStatus status,
        int progress,
        String resultRef,
        String errorCode,
        int retryCount,
        long version,
        Instant createdAt,
        Instant startedAt,
        Instant finishedAt
) {
    public static TaskView from(BizTask task) {
        return new TaskView(
                String.valueOf(task.getId()),
                String.valueOf(task.getOwnerId()),
                task.getConversationId() == null
                        ? null
                        : String.valueOf(task.getConversationId()),
                task.getType(),
                task.getOperationId(),
                task.getStatus(),
                task.getProgress(),
                task.getResultRef(),
                task.getErrorCode(),
                task.getRetryCount(),
                task.getVersion(),
                task.getCreatedAt(),
                task.getStartedAt(),
                task.getFinishedAt()
        );
    }
}
