package com.livestock.platform.knowledge.api;

import com.livestock.platform.knowledge.domain.KnowledgeDocument;
import com.livestock.platform.knowledge.domain.KnowledgeDocumentStatus;
import java.time.Instant;

public record KnowledgeDocumentView(
        String id,
        String ownerId,
        String fileName,
        String mediaType,
        long sizeBytes,
        String sha256,
        String collection,
        KnowledgeDocumentStatus status,
        String taskId,
        String ragDocumentId,
        String executionMode,
        Integer chunkCount,
        Instant createdAt,
        Instant updatedAt,
        Instant indexedAt
) {
    public static KnowledgeDocumentView from(KnowledgeDocument document) {
        return new KnowledgeDocumentView(
                document.getDocumentId(),
                String.valueOf(document.getOwnerId()),
                document.getFileName(),
                document.getMediaType(),
                document.getSizeBytes(),
                document.getSha256(),
                document.getCollection(),
                document.getStatus(),
                document.getIndexTaskId() == null ? null : String.valueOf(document.getIndexTaskId()),
                document.getRagDocumentId(),
                document.getExecutionMode(),
                document.getChunkCount(),
                document.getCreatedAt(),
                document.getUpdatedAt(),
                document.getIndexedAt()
        );
    }
}
