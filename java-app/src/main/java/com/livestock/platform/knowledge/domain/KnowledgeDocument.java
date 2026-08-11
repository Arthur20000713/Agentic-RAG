package com.livestock.platform.knowledge.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Instant;
import java.util.Objects;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "knowledge_document")
public class KnowledgeDocument {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "document_id", nullable = false, length = 128)
    private String documentId;

    @Column(name = "owner_id", nullable = false)
    private Long ownerId;

    @Column(name = "client_idempotency_key", nullable = false, length = 128)
    private String clientIdempotencyKey;

    @Column(name = "operation_id", nullable = false, length = 128)
    private String operationId;

    @Column(name = "original_request_id", nullable = false, length = 128)
    private String originalRequestId;

    @Column(name = "collection_name", nullable = false, length = 128)
    private String collection;

    @Column(name = "object_key", nullable = false, length = 512)
    private String objectKey;

    @Column(name = "file_name", nullable = false, length = 255)
    private String fileName;

    @Column(name = "media_type", nullable = false, length = 128)
    private String mediaType;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    @Column(name = "sha256", nullable = false, length = 64)
    private String sha256;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 32)
    private KnowledgeDocumentStatus status;

    @Column(name = "index_task_id")
    private Long indexTaskId;

    @Column(name = "rag_document_id", length = 64)
    private String ragDocumentId;

    @Column(name = "execution_mode", length = 8)
    private String executionMode;

    @Column(name = "chunk_count")
    private Integer chunkCount;

    @Column(name = "index_deadline_at", nullable = false)
    private Instant indexDeadlineAt;

    @Column(name = "indexed_at")
    private Instant indexedAt;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected KnowledgeDocument() {
    }

    public KnowledgeDocument(
            String documentId,
            Long ownerId,
            String clientIdempotencyKey,
            String operationId,
            String originalRequestId,
            String collection,
            String objectKey,
            String fileName,
            String mediaType,
            long sizeBytes,
            String sha256,
            Instant indexDeadlineAt
    ) {
        this.documentId = requireText(documentId, "documentId");
        this.ownerId = Objects.requireNonNull(ownerId, "ownerId");
        this.clientIdempotencyKey = requireText(clientIdempotencyKey, "clientIdempotencyKey");
        this.operationId = requireText(operationId, "operationId");
        this.originalRequestId = requireText(originalRequestId, "originalRequestId");
        this.collection = requireText(collection, "collection");
        this.objectKey = requireText(objectKey, "objectKey");
        this.fileName = requireText(fileName, "fileName");
        this.mediaType = requireText(mediaType, "mediaType");
        if (sizeBytes <= 0) {
            throw new IllegalArgumentException("sizeBytes must be positive");
        }
        this.sizeBytes = sizeBytes;
        this.sha256 = requireText(sha256, "sha256");
        this.indexDeadlineAt = Objects.requireNonNull(indexDeadlineAt, "indexDeadlineAt");
        this.status = KnowledgeDocumentStatus.UPLOADED;
    }

    public void attachTask(Long taskId) {
        this.indexTaskId = Objects.requireNonNull(taskId, "taskId");
    }

    public void markIndexing() {
        status = KnowledgeDocumentStatus.INDEXING;
    }

    public void markIndexed(String nextRagDocumentId, String nextExecutionMode, Integer nextChunkCount, Instant now) {
        status = "REAL".equals(nextExecutionMode)
                ? KnowledgeDocumentStatus.INDEXED
                : KnowledgeDocumentStatus.VALIDATED;
        ragDocumentId = requireText(nextRagDocumentId, "ragDocumentId");
        executionMode = requireText(nextExecutionMode, "executionMode");
        chunkCount = nextChunkCount;
        indexedAt = Objects.requireNonNull(now, "now");
    }

    public void markFailed(KnowledgeDocumentStatus nextStatus) {
        if (nextStatus != KnowledgeDocumentStatus.FAILED
                && nextStatus != KnowledgeDocumentStatus.TIMED_OUT
                && nextStatus != KnowledgeDocumentStatus.CANCELLED) {
            throw new IllegalArgumentException("document terminal status is invalid");
        }
        status = nextStatus;
    }

    private static String requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value;
    }

    public Long getId() { return id; }
    public String getDocumentId() { return documentId; }
    public Long getOwnerId() { return ownerId; }
    public String getClientIdempotencyKey() { return clientIdempotencyKey; }
    public String getOperationId() { return operationId; }
    public String getOriginalRequestId() { return originalRequestId; }
    public String getCollection() { return collection; }
    public String getObjectKey() { return objectKey; }
    public String getFileName() { return fileName; }
    public String getMediaType() { return mediaType; }
    public long getSizeBytes() { return sizeBytes; }
    public String getSha256() { return sha256; }
    public KnowledgeDocumentStatus getStatus() { return status; }
    public Long getIndexTaskId() { return indexTaskId; }
    public String getRagDocumentId() { return ragDocumentId; }
    public String getExecutionMode() { return executionMode; }
    public Integer getChunkCount() { return chunkCount; }
    public Instant getIndexDeadlineAt() { return indexDeadlineAt; }
    public Instant getIndexedAt() { return indexedAt; }
    public long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
