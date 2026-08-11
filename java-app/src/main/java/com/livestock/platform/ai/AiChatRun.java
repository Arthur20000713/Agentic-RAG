package com.livestock.platform.ai;

import java.time.OffsetDateTime;

public record AiChatRun(
        String requestId,
        String operationId,
        String runId,
        String type,
        Status status,
        AiChatResponse result,
        AiErrorDetail error,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        OffsetDateTime expiresAt
) {

    public enum Status {
        RUNNING,
        SUCCEEDED,
        FAILED
    }
}
