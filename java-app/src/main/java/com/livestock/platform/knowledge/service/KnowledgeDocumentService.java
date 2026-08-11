package com.livestock.platform.knowledge.service;

import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.knowledge.api.DocumentUploadResponse;
import com.livestock.platform.knowledge.api.KnowledgeDocumentView;
import com.livestock.platform.knowledge.domain.KnowledgeDocument;
import com.livestock.platform.knowledge.repository.KnowledgeDocumentRepository;
import com.livestock.platform.knowledge.storage.SharedVolumeObjectStore;
import com.livestock.platform.knowledge.storage.SharedVolumeObjectStore.StoredObject;
import com.livestock.platform.security.UserPrincipal;
import com.livestock.platform.task.api.TaskView;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

@Service
public class KnowledgeDocumentService {

    private final SharedVolumeObjectStore objectStore;
    private final DocumentUploadTransactionService transactionService;
    private final KnowledgeDocumentRepository documentRepository;

    public KnowledgeDocumentService(
            SharedVolumeObjectStore objectStore,
            DocumentUploadTransactionService transactionService,
            KnowledgeDocumentRepository documentRepository
    ) {
        this.objectStore = objectStore;
        this.transactionService = transactionService;
        this.documentRepository = documentRepository;
    }

    public DocumentUploadResponse upload(
            MultipartFile file,
            String clientKey,
            UserPrincipal actor,
            AuditRequestMetadata metadata
    ) {
        Long ownerId = Long.valueOf(actor.userId());
        StoredObject stored = objectStore.store(ownerId, file);
        try {
            DocumentUploadTransactionService.CreationResult result =
                    transactionService.createOrReplay(
                            ownerId,
                            clientKey,
                            "doc_" + UUID.randomUUID(),
                            "op_doc_" + UUID.randomUUID(),
                            RequestIds.current(),
                            stored,
                            metadata
                    );
            if (result.replay()) {
                objectStore.deleteQuietly(stored.absolutePath());
            }
            return new DocumentUploadResponse(
                    KnowledgeDocumentView.from(result.document()),
                    TaskView.from(result.task()),
                    result.replay()
            );
        } catch (RuntimeException exception) {
            objectStore.deleteQuietly(stored.absolutePath());
            throw exception;
        }
    }

    @Transactional(readOnly = true)
    public KnowledgeDocumentView get(String documentId, UserPrincipal actor) {
        KnowledgeDocument document;
        if (actor.authorities().contains("TASK_MANAGE")) {
            document = documentRepository.findByDocumentId(documentId)
                    .orElseThrow(KnowledgeDocumentService::notFound);
        } else {
            document = documentRepository.findByDocumentIdAndOwnerId(
                            documentId,
                            Long.valueOf(actor.userId())
                    )
                    .orElseThrow(KnowledgeDocumentService::notFound);
        }
        return KnowledgeDocumentView.from(document);
    }

    private static ApiException notFound() {
        return new ApiException(
                HttpStatus.NOT_FOUND,
                "DOCUMENT_NOT_FOUND",
                "The document was not found"
        );
    }
}
