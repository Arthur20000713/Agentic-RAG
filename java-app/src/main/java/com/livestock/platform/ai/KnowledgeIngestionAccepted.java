package com.livestock.platform.ai;

import java.time.Instant;

public record KnowledgeIngestionAccepted(
        String requestId,
        String operationId,
        String runId,
        String type,
        DocumentIndexOperation.Status status,
        Instant submittedAt
) {
}
