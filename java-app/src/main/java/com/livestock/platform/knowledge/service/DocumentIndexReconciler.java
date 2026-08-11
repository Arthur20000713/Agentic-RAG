package com.livestock.platform.knowledge.service;

import com.livestock.platform.ai.DocumentIndexOperation;
import com.livestock.platform.ai.KnowledgeClientException;
import com.livestock.platform.ai.KnowledgeIngestionAccepted;
import com.livestock.platform.ai.PythonKnowledgeClient;
import com.livestock.platform.knowledge.KnowledgeProperties;
import com.livestock.platform.task.domain.BizTask;
import com.livestock.platform.task.domain.TaskStatus;
import com.livestock.platform.task.domain.TaskType;
import com.livestock.platform.task.repository.BizTaskRepository;
import java.util.EnumSet;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
public class DocumentIndexReconciler {

    private static final Logger LOGGER = LoggerFactory.getLogger(DocumentIndexReconciler.class);
    private static final EnumSet<TaskStatus> ACTIVE = EnumSet.of(
            TaskStatus.CREATED,
            TaskStatus.RUNNING,
            TaskStatus.SUBMIT_UNKNOWN
    );

    private final BizTaskRepository taskRepository;
    private final DocumentIndexTransactionService transactions;
    private final PythonKnowledgeClient client;
    private final KnowledgeProperties properties;

    public DocumentIndexReconciler(
            BizTaskRepository taskRepository,
            DocumentIndexTransactionService transactions,
            PythonKnowledgeClient client,
            KnowledgeProperties properties
    ) {
        this.taskRepository = taskRepository;
        this.transactions = transactions;
        this.client = client;
        this.properties = properties;
    }

    @Scheduled(fixedDelayString = "${livestock.knowledge.reconciliation-delay-millis:1000}")
    public void reconcile() {
        if (!properties.reconciliationEnabled()) {
            return;
        }
        for (BizTask task : taskRepository.findAllByTypeAndStatusIn(
                TaskType.DOCUMENT_INDEX,
                ACTIVE,
                PageRequest.of(0, 20, Sort.by("createdAt").ascending())
        )) {
            reconcileOne(task.getId());
        }
    }

    void reconcileOne(Long taskId) {
        DocumentIndexTransactionService.SubmissionSnapshot snapshot = transactions.prepare(taskId);
        if (snapshot == null) {
            return;
        }
        try {
            if (snapshot.firstSubmission()) {
                submit(snapshot);
                return;
            }
            Optional<DocumentIndexOperation> operation = client.findOperation(
                    snapshot.request().requestId(),
                    snapshot.request().operationId()
            );
            if (operation.isPresent()) {
                transactions.applyOperation(taskId, operation.get());
            } else {
                submit(snapshot);
            }
        } catch (KnowledgeClientException exception) {
            if (exception.submissionUnknown() || exception.retryable()) {
                transactions.markSubmissionUnknown(taskId, exception.code());
            } else {
                transactions.markSubmissionFailed(taskId, exception.code());
            }
        } catch (RuntimeException exception) {
            LOGGER.error("Document reconciliation failed taskId={}", taskId, exception);
        }
    }

    private void submit(DocumentIndexTransactionService.SubmissionSnapshot snapshot) {
        KnowledgeIngestionAccepted accepted = client.submit(snapshot.request());
        transactions.recordAccepted(snapshot.taskId(), accepted);
        if (accepted.status() == DocumentIndexOperation.Status.SUCCEEDED
                || accepted.status() == DocumentIndexOperation.Status.FAILED
                || accepted.status() == DocumentIndexOperation.Status.TIMED_OUT
                || accepted.status() == DocumentIndexOperation.Status.CANCELLED) {
            client.findOperation(
                    snapshot.request().requestId(),
                    snapshot.request().operationId()
            ).ifPresent(operation -> transactions.applyOperation(snapshot.taskId(), operation));
        }
    }
}
