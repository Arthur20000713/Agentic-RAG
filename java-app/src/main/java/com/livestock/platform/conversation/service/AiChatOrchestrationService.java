package com.livestock.platform.conversation.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.ai.AiChatClientException;
import com.livestock.platform.ai.AiChatRequest;
import com.livestock.platform.ai.AiChatResponse;
import com.livestock.platform.ai.AiChatRun;
import com.livestock.platform.ai.AiServiceProperties;
import com.livestock.platform.ai.PythonAiChatClient;
import com.livestock.platform.ai.context.RedisAiContextStore;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.conversation.api.MessageSubmissionResponse;
import com.livestock.platform.conversation.service.AiQueryTransactionService.AiExecution;
import com.livestock.platform.conversation.service.AiQueryTransactionService.AiQueryResult;
import com.livestock.platform.conversation.service.AiQueryTransactionService.PreparedAiQuery;
import com.livestock.platform.security.UserPrincipal;
import com.livestock.platform.task.domain.TaskStatus;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

@Service
public class AiChatOrchestrationService {

    private static final int CHAT_DEADLINE_MS = 60_000;
    private static final Set<String> RECONCILABLE_CODES = Set.of(
            "AI_BUSY",
            "AI_PROTOCOL_ERROR",
            "AI_SERVICE_UNAVAILABLE",
            "AI_TIMEOUT"
    );

    private final AiQueryTransactionService transactions;
    private final PythonAiChatClient aiClient;
    private final RedisAiContextStore contextStore;
    private final ObjectMapper objectMapper;
    private final AiServiceProperties properties;

    public AiChatOrchestrationService(
            AiQueryTransactionService transactions,
            PythonAiChatClient aiClient,
            RedisAiContextStore contextStore,
            ObjectMapper objectMapper,
            AiServiceProperties properties
    ) {
        this.transactions = transactions;
        this.aiClient = aiClient;
        this.contextStore = contextStore;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    public MessageSubmissionResponse execute(
            MessageSubmissionResponse submission,
            UserPrincipal actor,
            AuditRequestMetadata metadata
    ) {
        requireEnabled();
        Long taskId = Long.valueOf(submission.task().id());
        Long ownerId = Long.valueOf(actor.userId());
        Long conversationId = Long.valueOf(submission.task().conversationId());
        String operationId = submission.task().operationId();
        TaskStatus status = submission.task().status();

        if (isTerminal(status)) {
            return response(
                    submission,
                    transactions.currentResult(
                            taskId,
                            ownerId,
                            conversationId,
                            operationId
                    )
            );
        }
        if (status == TaskStatus.RUNNING
                || status == TaskStatus.SUBMIT_UNKNOWN) {
            PreparedAiQuery prepared = transactions.prepareForReconciliation(
                    taskId,
                    ownerId,
                    conversationId,
                    operationId
            );
            AiExecution execution = prepared.execution();
            return response(
                    submission,
                    isTerminal(execution.taskStatus())
                            ? transactions.currentResult(
                            execution.taskId(),
                            execution.ownerId(),
                            execution.conversationId(),
                            execution.operationId()
                    )
                            : reconcile(prepared, null, metadata, true)
            );
        }

        PreparedAiQuery prepared = transactions.start(
                taskId,
                ownerId,
                conversationId,
                operationId,
                submission.task().version(),
                metadata
        );
        AiExecution execution = prepared.execution();
        if (!prepared.submitRequired()) {
            AiQueryResult existing = isTerminal(execution.taskStatus())
                    ? transactions.currentResult(
                    execution.taskId(),
                    execution.ownerId(),
                    execution.conversationId(),
                    execution.operationId()
            )
                    : reconcile(prepared, null, metadata, true);
            return response(submission, existing);
        }

        return response(submission, dispatch(prepared, metadata));
    }

    private AiQueryResult dispatch(
            PreparedAiQuery prepared,
            AuditRequestMetadata metadata
    ) {
        AiExecution execution = prepared.execution();
        JsonNode context = contextStore.get(
                        execution.ownerId(),
                        execution.conversationId(),
                        execution.contextVersion()
                )
                .orElseGet(this::emptyContext);
        AiChatRequest request = new AiChatRequest(
                execution.originalRequestId(),
                execution.operationId(),
                String.valueOf(execution.conversationId()),
                String.valueOf(execution.ownerId()),
                prepared.query(),
                null,
                prepared.history(),
                context,
                execution.contextVersion(),
                CHAT_DEADLINE_MS
        );
        try {
            AiChatResponse aiResponse = aiClient.chat(request);
            return transactions.completeSuccess(execution, aiResponse, metadata);
        } catch (AiChatClientException failure) {
            return handleFailure(prepared, failure, metadata);
        }
    }

    public void requireEnabled() {
        if (!properties.chatEnabled()) {
            throw new ApiException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "AI_CHAT_DISABLED",
                    "AI chat is temporarily disabled"
            );
        }
    }

    private AiQueryResult handleFailure(
            PreparedAiQuery prepared,
            AiChatClientException failure,
            AuditRequestMetadata metadata
    ) {
        AiExecution execution = prepared.execution();
        if (shouldReconcile(failure)) {
            AiExecution unknown = transactions.markUnknown(
                    execution,
                    failure.code(),
                    metadata
            );
            return reconcile(
                    new PreparedAiQuery(
                            unknown,
                            prepared.query(),
                            prepared.history(),
                            false
                    ),
                    failure,
                    metadata,
                    false
            );
        }
        return transactions.completeFailure(
                execution,
                "AI_TIMEOUT".equals(failure.code())
                        ? TaskStatus.TIMED_OUT
                        : TaskStatus.FAILED,
                failure.code(),
                metadata
        );
    }

    private AiQueryResult reconcile(
            PreparedAiQuery prepared,
            AiChatClientException originalFailure,
            AuditRequestMetadata metadata,
            boolean redispatchAllowed
    ) {
        AiExecution execution = prepared.execution();
        Optional<AiChatRun> run;
        try {
            run = aiClient.findRun(RequestIds.current(), execution.operationId());
        } catch (AiChatClientException reconciliationFailure) {
            return transactions.currentResult(
                    execution.taskId(),
                    execution.ownerId(),
                    execution.conversationId(),
                    execution.operationId()
            );
        }
        if (run.isEmpty()) {
            if (originalFailure != null && !originalFailure.submissionUnknown()) {
                return transactions.completeFailure(
                        execution,
                        TaskStatus.FAILED,
                        originalFailure.code(),
                        metadata
                );
            }
            if (redispatchAllowed) {
                return dispatch(prepared, metadata);
            }
            return transactions.currentResult(
                    execution.taskId(),
                    execution.ownerId(),
                    execution.conversationId(),
                    execution.operationId()
            );
        }
        AiChatRun executionRecord = run.orElseThrow();
        return switch (executionRecord.status()) {
            case RUNNING -> redispatchAllowed
                    && recoveryLeaseExpired(executionRecord)
                    ? dispatch(prepared, metadata)
                    : transactions.currentResult(
                            execution.taskId(),
                            execution.ownerId(),
                            execution.conversationId(),
                            execution.operationId()
                    );
            case SUCCEEDED -> transactions.completeSuccess(
                    execution,
                    executionRecord.result(),
                    metadata
            );
            case FAILED -> transactions.completeFailure(
                    execution,
                    TaskStatus.FAILED,
                    executionRecord.error().code(),
                    metadata
            );
        };
    }

    private boolean recoveryLeaseExpired(AiChatRun run) {
        return !run.updatedAt()
                .plus(properties.recoveryLease())
                .isAfter(OffsetDateTime.now());
    }

    private MessageSubmissionResponse response(
            MessageSubmissionResponse submission,
            AiQueryResult result
    ) {
        return new MessageSubmissionResponse(
                submission.message(),
                result.assistantMessage(),
                result.task(),
                submission.replayed()
        );
    }

    private JsonNode emptyContext() {
        return objectMapper.createObjectNode()
                .put("schemaVersion", 1)
                .set("slots", objectMapper.createObjectNode());
    }

    private static boolean shouldReconcile(AiChatClientException failure) {
        return failure.submissionUnknown()
                || failure.remoteCode() != null
                && RECONCILABLE_CODES.contains(failure.code());
    }

    private static boolean isTerminal(TaskStatus status) {
        return status == TaskStatus.SUCCEEDED
                || status == TaskStatus.FAILED
                || status == TaskStatus.TIMED_OUT
                || status == TaskStatus.CANCELLED;
    }
}
