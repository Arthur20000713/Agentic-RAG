package com.livestock.platform.ai;

public record KnowledgeIngestionRequest(
        String requestId,
        String operationId,
        String userId,
        String documentId,
        String collection,
        String objectKey,
        String fileName,
        String mediaType,
        long sizeBytes,
        String sha256,
        boolean force
) {
}
