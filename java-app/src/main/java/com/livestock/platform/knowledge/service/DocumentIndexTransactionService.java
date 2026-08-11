package com.livestock.platform.knowledge.service;

import com.livestock.platform.ai.DocumentIndexOperation;
import com.livestock.platform.ai.DocumentIndexResult;
import com.livestock.platform.ai.KnowledgeIngestionAccepted;
import com.livestock.platform.ai.KnowledgeIngestionRequest;
import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.knowledge.domain.KnowledgeDocument;
import com.livestock.platform.knowledge.domain.KnowledgeDocumentStatus;
import com.livestock.platform.knowledge.repository.KnowledgeDocumentRepository;
import com.livestock.platform.task.domain.BizTask;
import com.livestock.platform.task.domain.TaskStatus;
import com.livestock.platform.task.domain.TaskType;
import com.livestock.platform.task.repository.BizTaskRepository;
import com.livestock.platform.task.service.TaskStateMachine;
import java.time.Clock;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentIndexTransactionService {

    private final BizTaskRepository taskRepository;
    private final KnowledgeDocumentRepository documentRepository;
    private final TaskStateMachine stateMachine;
    private final AuditService auditService;
    private final Clock clock;

    public DocumentIndexTransactionService(
            BizTaskRepository taskRepository,
            KnowledgeDocumentRepository documentRepository,
            TaskStateMachine stateMachine,
            AuditService auditService,
            Clock clock
    ) {
        this.taskRepository = taskRepository;
        this.documentRepository = documentRepository;
        this.stateMachine = stateMachine;
        this.auditService = auditService;
        this.clock = clock;
    }

    @Transactional
    public SubmissionSnapshot prepare(Long taskId) {
        Locked locked = lock(taskId);
        BizTask task = locked.task();
        KnowledgeDocument document = locked.document();
        if (terminal(task.getStatus())) {
            return null;
        }
        if (!document.getIndexDeadlineAt().isAfter(clock.instant())) {
            finishFailure(locked, TaskStatus.TIMED_OUT, "DOCUMENT_INDEX_DEADLINE_EXCEEDED");
            return null;
        }
        boolean firstSubmission = task.getStatus() == TaskStatus.CREATED;
        if (firstSubmission) {
            stateMachine.requireTransition(task.getStatus(), TaskStatus.RUNNING);
            task.applyTransition(TaskStatus.RUNNING, 5, null, null, clock.instant());
            document.markIndexing();
            taskRepository.saveAndFlush(task);
            documentRepository.saveAndFlush(document);
            appendAudit(locked, "DOCUMENT_INDEX_STARTED", Map.of("progress", 5));
        }
        return snapshot(task, document, firstSubmission);
    }

    @Transactional
    public void recordAccepted(Long taskId, KnowledgeIngestionAccepted accepted) {
        Locked locked = lock(taskId);
        BizTask task = locked.task();
        if (terminal(task.getStatus())) {
            return;
        }
        requireOperation(locked, accepted.operationId());
        requireRunId(task, accepted.runId());
        task.setExecutorJobId(accepted.runId());
        if (accepted.status() == DocumentIndexOperation.Status.ACCEPTED
                || accepted.status() == DocumentIndexOperation.Status.RUNNING) {
            stateMachine.requireTransition(task.getStatus(), TaskStatus.RUNNING);
            task.applyTransition(
                    TaskStatus.RUNNING,
                    Math.max(task.getProgress(), 10),
                    null,
                    null,
                    clock.instant()
            );
        }
        taskRepository.saveAndFlush(task);
    }

    @Transactional
    public void applyOperation(Long taskId, DocumentIndexOperation operation) {
        Locked locked = lock(taskId);
        BizTask task = locked.task();
        if (terminal(task.getStatus())) {
            return;
        }
        requireOperation(locked, operation.operationId());
        requireRunId(task, operation.runId());
        task.setExecutorJobId(operation.runId());
        switch (operation.status()) {
            case ACCEPTED, RUNNING -> {
                stateMachine.requireTransition(task.getStatus(), TaskStatus.RUNNING);
                task.applyTransition(
                        TaskStatus.RUNNING,
                        Math.max(task.getProgress(), operation.progress()),
                        null,
                        null,
                        clock.instant()
                );
                locked.document().markIndexing();
            }
            case SUCCEEDED -> completeSuccess(locked, operation.result());
            case FAILED -> finishFailure(locked, TaskStatus.FAILED, errorCode(operation));
            case TIMED_OUT -> finishFailure(locked, TaskStatus.TIMED_OUT, errorCode(operation));
            case CANCELLED -> finishFailure(locked, TaskStatus.CANCELLED, errorCode(operation));
        }
        taskRepository.saveAndFlush(task);
        documentRepository.saveAndFlush(locked.document());
    }

    @Transactional
    public void markSubmissionUnknown(Long taskId, String errorCode) {
        Locked locked = lock(taskId);
        BizTask task = locked.task();
        if (terminal(task.getStatus()) || task.getStatus() == TaskStatus.SUBMIT_UNKNOWN) {
            return;
        }
        stateMachine.requireTransition(task.getStatus(), TaskStatus.SUBMIT_UNKNOWN);
        task.applyTransition(
                TaskStatus.SUBMIT_UNKNOWN,
                Math.max(task.getProgress(), 10),
                null,
                bounded(errorCode),
                clock.instant()
        );
        task.incrementRetryCount();
        taskRepository.saveAndFlush(task);
        appendAudit(
                locked,
                "DOCUMENT_INDEX_SUBMISSION_UNKNOWN",
                Map.of("errorCode", bounded(errorCode))
        );
    }

    @Transactional
    public void markSubmissionFailed(Long taskId, String errorCode) {
        Locked locked = lock(taskId);
        if (!terminal(locked.task().getStatus())) {
            finishFailure(locked, TaskStatus.FAILED, errorCode);
        }
    }

    private void completeSuccess(Locked locked, DocumentIndexResult result) {
        if (result == null
                || !locked.document().getDocumentId().equals(result.documentId())
                || !locked.document().getCollection().equals(result.collection())
                || result.ragDocumentId() == null
                || result.executionMode() == null) {
            finishFailure(locked, TaskStatus.FAILED, "AI_PROTOCOL_ERROR");
            return;
        }
        BizTask task = locked.task();
        stateMachine.requireTransition(task.getStatus(), TaskStatus.SUCCEEDED);
        task.applyTransition(
                TaskStatus.SUCCEEDED,
                100,
                "document:" + locked.document().getDocumentId(),
                null,
                clock.instant()
        );
        locked.document().markIndexed(
                result.ragDocumentId(),
                result.executionMode().name(),
                result.chunkCount(),
                clock.instant()
        );
        appendAudit(
                locked,
                "DOCUMENT_INDEX_COMPLETED",
                Map.of(
                        "executionMode", result.executionMode(),
                        "indexed", result.indexed(),
                        "skipped", result.skipped()
                )
        );
    }

    private void finishFailure(Locked locked, TaskStatus status, String errorCode) {
        BizTask task = locked.task();
        stateMachine.requireTransition(task.getStatus(), status);
        task.applyTransition(status, 100, null, bounded(errorCode), clock.instant());
        locked.document().markFailed(switch (status) {
            case TIMED_OUT -> KnowledgeDocumentStatus.TIMED_OUT;
            case CANCELLED -> KnowledgeDocumentStatus.CANCELLED;
            default -> KnowledgeDocumentStatus.FAILED;
        });
        taskRepository.saveAndFlush(task);
        documentRepository.saveAndFlush(locked.document());
        appendAudit(
                locked,
                "DOCUMENT_INDEX_FAILED",
                Map.of("status", status, "errorCode", bounded(errorCode))
        );
    }

    private Locked lock(Long taskId) {
        BizTask task = taskRepository.findByIdForUpdate(taskId)
                .filter(value -> value.getType() == TaskType.DOCUMENT_INDEX)
                .orElseThrow(() -> new IllegalStateException("document index task is missing"));
        KnowledgeDocument document = documentRepository.findByIndexTaskIdForUpdate(taskId)
                .orElseThrow(() -> new IllegalStateException("task document is missing"));
        return new Locked(task, document);
    }

    private static SubmissionSnapshot snapshot(
            BizTask task,
            KnowledgeDocument document,
            boolean firstSubmission
    ) {
        return new SubmissionSnapshot(
                task.getId(),
                firstSubmission,
                new KnowledgeIngestionRequest(
                        document.getOriginalRequestId(),
                        document.getOperationId(),
                        String.valueOf(document.getOwnerId()),
                        document.getDocumentId(),
                        document.getCollection(),
                        document.getObjectKey(),
                        document.getFileName(),
                        document.getMediaType(),
                        document.getSizeBytes(),
                        document.getSha256(),
                        false
                )
        );
    }

    private static void requireOperation(Locked locked, String operationId) {
        if (!locked.task().getOperationId().equals(operationId)
                || !locked.document().getOperationId().equals(operationId)) {
            throw new IllegalStateException("document operation does not match task");
        }
    }

    private static void requireRunId(BizTask task, String runId) {
        if (runId == null || runId.isBlank()
                || (task.getExecutorJobId() != null
                && !task.getExecutorJobId().equals(runId))) {
            throw new IllegalStateException("document execution run ID changed");
        }
    }

    private void appendAudit(Locked locked, String action, Map<String, ?> details) {
        KnowledgeDocument document = locked.document();
        auditService.append(new AuditEvent(
                document.getOwnerId(),
                action,
                "KNOWLEDGE_DOCUMENT",
                document.getDocumentId(),
                document.getOriginalRequestId(),
                "SUCCESS",
                null,
                "document-index-reconciler",
                details
        ));
    }

    private static String errorCode(DocumentIndexOperation operation) {
        return operation.error() == null ? "DOCUMENT_INDEX_FAILED" : operation.error().code();
    }

    private static String bounded(String value) {
        String safe = value == null || value.isBlank() ? "DOCUMENT_INDEX_FAILED" : value;
        return safe.length() <= 128 ? safe : safe.substring(0, 128);
    }

    private static boolean terminal(TaskStatus status) {
        return status == TaskStatus.SUCCEEDED
                || status == TaskStatus.FAILED
                || status == TaskStatus.TIMED_OUT
                || status == TaskStatus.CANCELLED;
    }

    public record SubmissionSnapshot(
            Long taskId,
            boolean firstSubmission,
            KnowledgeIngestionRequest request
    ) {
    }

    private record Locked(BizTask task, KnowledgeDocument document) {
    }
}
