package com.livestock.platform.knowledge.service;

import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.knowledge.KnowledgeProperties;
import com.livestock.platform.knowledge.domain.KnowledgeDocument;
import com.livestock.platform.knowledge.repository.KnowledgeDocumentRepository;
import com.livestock.platform.knowledge.storage.SharedVolumeObjectStore.StoredObject;
import com.livestock.platform.task.domain.BizTask;
import com.livestock.platform.task.domain.TaskType;
import com.livestock.platform.task.repository.BizTaskRepository;
import com.livestock.platform.task.service.IdempotencyHasher;
import java.time.Clock;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentUploadTransactionService {

    private final KnowledgeDocumentRepository documentRepository;
    private final BizTaskRepository taskRepository;
    private final IdempotencyHasher hasher;
    private final AuditService auditService;
    private final KnowledgeProperties properties;
    private final Clock clock;

    public DocumentUploadTransactionService(
            KnowledgeDocumentRepository documentRepository,
            BizTaskRepository taskRepository,
            IdempotencyHasher hasher,
            AuditService auditService,
            KnowledgeProperties properties,
            Clock clock
    ) {
        this.documentRepository = documentRepository;
        this.taskRepository = taskRepository;
        this.hasher = hasher;
        this.auditService = auditService;
        this.properties = properties;
        this.clock = clock;
    }

    @Transactional
    public CreationResult createOrReplay(
            Long ownerId,
            String clientKey,
            String documentId,
            String operationId,
            String originalRequestId,
            StoredObject stored,
            AuditRequestMetadata metadata
    ) {
        String requestHash = requestHash(stored);
        KnowledgeDocument existing = documentRepository
                .findByOwnerIdAndClientIdempotencyKey(ownerId, clientKey)
                .orElse(null);
        if (existing != null) {
            BizTask task = taskRepository.findById(existing.getIndexTaskId())
                    .orElseThrow(() -> new IllegalStateException("document task is missing"));
            if (!requestHash.equals(task.getRequestHash())) {
                throw new ApiException(
                        HttpStatus.CONFLICT,
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key is already bound to another document"
                );
            }
            return new CreationResult(existing, task, true);
        }

        KnowledgeDocument document = documentRepository.saveAndFlush(
                new KnowledgeDocument(
                        documentId,
                        ownerId,
                        clientKey,
                        operationId,
                        originalRequestId,
                        properties.collection(),
                        stored.objectKey(),
                        stored.fileName(),
                        stored.mediaType(),
                        stored.sizeBytes(),
                        stored.sha256(),
                        clock.instant().plus(properties.indexDeadline())
                )
        );
        BizTask task = taskRepository.saveAndFlush(new BizTask(
                ownerId,
                null,
                TaskType.DOCUMENT_INDEX,
                operationId,
                requestHash
        ));
        document.attachTask(task.getId());
        documentRepository.saveAndFlush(document);
        auditService.append(new AuditEvent(
                ownerId,
                "DOCUMENT_UPLOADED",
                "KNOWLEDGE_DOCUMENT",
                document.getDocumentId(),
                RequestIds.current(),
                "SUCCESS",
                metadata.clientIp(),
                metadata.userAgent(),
                Map.of(
                        "taskId", task.getId(),
                        "collection", document.getCollection(),
                        "sizeBytes", document.getSizeBytes(),
                        "sha256", document.getSha256(),
                        "idempotencyKeyDigest", hasher.keyDigest(clientKey)
                )
        ));
        return new CreationResult(document, task, false);
    }

    private String requestHash(StoredObject stored) {
        return hasher.documentRequestHash(
                properties.collection(),
                stored.fileName(),
                stored.mediaType(),
                stored.sizeBytes(),
                stored.sha256()
        );
    }

    public record CreationResult(
            KnowledgeDocument document,
            BizTask task,
            boolean replay
    ) {
    }
}
