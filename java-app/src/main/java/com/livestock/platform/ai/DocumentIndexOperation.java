package com.livestock.platform.ai;

import java.time.Instant;

public record DocumentIndexOperation(
        String requestId,
        String operationId,
        String runId,
        String type,
        Status status,
        int progress,
        DocumentIndexResult result,
        AiErrorDetail error,
        Instant createdAt,
        Instant startedAt,
        Instant updatedAt,
        Instant finishedAt,
        Instant expiresAt
) {
    public enum Status {
        ACCEPTED,
        RUNNING,
        SUCCEEDED,
        FAILED,
        TIMED_OUT,
        CANCELLED
    }
}
