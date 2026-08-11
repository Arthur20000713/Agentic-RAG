package com.livestock.platform.conversation.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.ai.AiChatRequest;
import com.livestock.platform.ai.AiChatResponse;
import com.livestock.platform.ai.context.RedisAiContextStore;
import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.conversation.api.MessageView;
import com.livestock.platform.conversation.domain.Conversation;
import com.livestock.platform.conversation.domain.ConversationMessage;
import com.livestock.platform.conversation.domain.EvidenceStatus;
import com.livestock.platform.conversation.domain.MessageRole;
import com.livestock.platform.conversation.domain.MessageStatus;
import com.livestock.platform.conversation.domain.RiskLevel;
import com.livestock.platform.conversation.repository.ConversationMessageRepository;
import com.livestock.platform.conversation.repository.ConversationRepository;
import com.livestock.platform.task.api.TaskView;
import com.livestock.platform.task.domain.BizTask;
import com.livestock.platform.task.domain.TaskStatus;
import com.livestock.platform.task.domain.TaskType;
import com.livestock.platform.task.repository.BizTaskRepository;
import com.livestock.platform.task.service.TaskStateMachine;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class AiQueryTransactionService {

    private static final TypeReference<List<Map<String, Object>>> SOURCE_LIST =
            new TypeReference<>() {
            };

    private final ConversationRepository conversationRepository;
    private final ConversationMessageRepository messageRepository;
    private final BizTaskRepository taskRepository;
    private final TaskStateMachine stateMachine;
    private final AuditService auditService;
    private final RedisAiContextStore contextStore;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    public AiQueryTransactionService(
            ConversationRepository conversationRepository,
            ConversationMessageRepository messageRepository,
            BizTaskRepository taskRepository,
            TaskStateMachine stateMachine,
            AuditService auditService,
            RedisAiContextStore contextStore,
            ObjectMapper objectMapper,
            Clock clock
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.taskRepository = taskRepository;
        this.stateMachine = stateMachine;
        this.auditService = auditService;
        this.contextStore = contextStore;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public PreparedAiQuery start(
            Long taskId,
            Long ownerId,
            Long conversationId,
            String operationId,
            long expectedTaskVersion,
            AuditRequestMetadata metadata
    ) {
        Conversation conversation = lockConversation(
                conversationId,
                ownerId
        );
        BizTask task = lockTask(
                taskId,
                ownerId,
                conversationId,
                operationId
        );
        ConversationMessage userMessage = userMessage(conversationId, operationId);
        if (task.getStatus() != TaskStatus.CREATED) {
            return new PreparedAiQuery(
                    execution(conversation, task, userMessage),
                    userMessage.getContent(),
                    history(conversationId, operationId),
                    false
            );
        }
        requireActiveOperation(conversation, operationId);
        if (task.getVersion() != expectedTaskVersion) {
            throw conflict("TASK_VERSION_CONFLICT", "The AI task version changed");
        }
        stateMachine.requireTransition(task.getStatus(), TaskStatus.RUNNING);
        task.applyTransition(
                TaskStatus.RUNNING,
                10,
                null,
                null,
                clock.instant()
        );
        taskRepository.saveAndFlush(task);
        appendAudit(
                ownerId,
                "AI_QUERY_STARTED",
                task,
                metadata,
                Map.of("conversationId", conversationId)
        );
        return new PreparedAiQuery(
                execution(conversation, task, userMessage),
                userMessage.getContent(),
                history(conversationId, operationId),
                true
        );
    }

    @Transactional
    public PreparedAiQuery prepareForReconciliation(
            Long taskId,
            Long ownerId,
            Long conversationId,
            String operationId
    ) {
        Conversation conversation = lockConversation(
                conversationId,
                ownerId
        );
        BizTask task = lockTask(
                taskId,
                ownerId,
                conversationId,
                operationId
        );
        if (!isTerminal(task.getStatus())) {
            requireActiveOperation(conversation, operationId);
        }
        ConversationMessage userMessage = userMessage(conversationId, operationId);
        return new PreparedAiQuery(
                execution(conversation, task, userMessage),
                userMessage.getContent(),
                history(conversationId, operationId),
                false
        );
    }

    @Transactional
    public AiExecution markUnknown(
            AiExecution expected,
            String errorCode,
            AuditRequestMetadata metadata
    ) {
        LockedState state = lockState(expected);
        BizTask task = state.task();
        requireActiveOperation(state.conversation(), expected.operationId());
        if (task.getStatus() == TaskStatus.SUBMIT_UNKNOWN) {
            return execution(state.conversation(), task, state.userMessage());
        }
        requireExpectedVersion(task, expected);
        stateMachine.requireTransition(task.getStatus(), TaskStatus.SUBMIT_UNKNOWN);
        task.applyTransition(
                TaskStatus.SUBMIT_UNKNOWN,
                Math.max(task.getProgress(), 25),
                null,
                boundedErrorCode(errorCode),
                clock.instant()
        );
        taskRepository.saveAndFlush(task);
        appendAudit(
                task.getOwnerId(),
                "AI_QUERY_SUBMISSION_UNKNOWN",
                task,
                metadata,
                Map.of("errorCode", boundedErrorCode(errorCode))
        );
        return execution(state.conversation(), task, state.userMessage());
    }

    @Transactional
    public AiQueryResult completeFailure(
            AiExecution expected,
            TaskStatus finalStatus,
            String errorCode,
            AuditRequestMetadata metadata
    ) {
        if (finalStatus != TaskStatus.FAILED && finalStatus != TaskStatus.TIMED_OUT) {
            throw new IllegalArgumentException("AI failure status is invalid");
        }
        LockedState state = lockState(expected);
        BizTask task = state.task();
        if (isTerminal(task.getStatus())) {
            return currentResult(state.conversation(), task);
        }
        requireActiveOperation(state.conversation(), expected.operationId());
        requireExpectedVersion(task, expected);
        stateMachine.requireTransition(task.getStatus(), finalStatus);
        task.applyTransition(
                finalStatus,
                task.getProgress(),
                null,
                boundedErrorCode(errorCode),
                clock.instant()
        );
        state.conversation().releaseOperation(expected.operationId());
        taskRepository.saveAndFlush(task);
        conversationRepository.saveAndFlush(state.conversation());
        appendAudit(
                task.getOwnerId(),
                "AI_QUERY_FAILED",
                task,
                metadata,
                Map.of(
                        "status", finalStatus,
                        "errorCode", boundedErrorCode(errorCode)
                )
        );
        return currentResult(state.conversation(), task);
    }

    @Transactional
    public AiQueryResult completeSuccess(
            AiExecution expected,
            AiChatResponse response,
            AuditRequestMetadata metadata
    ) {
        LockedState state = lockState(expected);
        BizTask task = state.task();
        Conversation conversation = state.conversation();
        validateResult(expected, response);
        String resultFingerprint = fingerprint(response);
        ConversationMessage existing = messageRepository
                .findByConversationIdAndTurnIdAndRole(
                        expected.conversationId(),
                        expected.operationId(),
                        MessageRole.ASSISTANT
                )
                .orElse(null);
        if (task.getStatus() == TaskStatus.SUCCEEDED) {
            if (existing != null
                    && resultFingerprint.equals(
                    existing.getMetadata().get("resultFingerprint")
            )) {
                return new AiQueryResult(
                        MessageView.from(existing),
                        TaskView.from(task)
                );
            }
            throw conflict(
                    "AI_RESULT_CONFLICT",
                    "The AI operation already has a different result"
            );
        }
        requireExpectedVersion(task, expected);
        if (task.getStatus() != TaskStatus.RUNNING
                && task.getStatus() != TaskStatus.SUBMIT_UNKNOWN) {
            throw conflict(
                    "AI_QUERY_NOT_COMPLETABLE",
                    "The AI query cannot accept a result in its current state"
            );
        }
        if (conversation.getContextVersion() != expected.contextVersion()
                || !Objects.equals(
                conversation.getActiveOperationId(),
                expected.operationId()
        )) {
            throw conflict(
                    "CONVERSATION_STATE_CONFLICT",
                    "The conversation state changed before the AI result completed"
            );
        }
        if (existing != null) {
            throw conflict(
                    "AI_RESULT_CONFLICT",
                    "The AI operation already has an assistant message"
            );
        }

        Instant completedAt = clock.instant();
        ConversationMessage assistant = messageRepository.saveAndFlush(
                new ConversationMessage(
                        expected.conversationId(),
                        expected.operationId(),
                        MessageRole.ASSISTANT,
                        response.answer(),
                        response.requestId(),
                        MessageStatus.COMPLETED,
                        response.intent(),
                        RiskLevel.valueOf(response.riskLevel().name()),
                        EvidenceStatus.valueOf(response.evidenceStatus().name()),
                        resultMetadata(response, resultFingerprint)
                )
        );
        stateMachine.requireTransition(task.getStatus(), TaskStatus.SUCCEEDED);
        task.setExecutorJobId(response.runId());
        task.applyTransition(
                TaskStatus.SUCCEEDED,
                100,
                "message:" + assistant.getId(),
                null,
                completedAt
        );
        conversation.completeOperation(expected.operationId(), completedAt);
        taskRepository.saveAndFlush(task);
        conversationRepository.saveAndFlush(conversation);
        appendAudit(
                task.getOwnerId(),
                "AI_QUERY_COMPLETED",
                task,
                metadata,
                Map.of(
                        "conversationId", expected.conversationId(),
                        "messageId", assistant.getId(),
                        "runId", response.runId(),
                        "traceId", response.traceId(),
                        "outcome", response.outcome(),
                        "evidenceStatus", response.evidenceStatus()
                )
        );
        registerContextWriteAfterCommit(
                expected.ownerId(),
                expected.conversationId(),
                response.contextVersion(),
                response.nextContext()
        );
        return new AiQueryResult(
                MessageView.from(assistant),
                TaskView.from(task)
        );
    }

    @Transactional(readOnly = true)
    public AiQueryResult currentResult(
            Long taskId,
            Long ownerId,
            Long conversationId,
            String operationId
    ) {
        BizTask task = taskRepository.findByIdAndOwnerId(taskId, ownerId)
                .filter(value -> Objects.equals(
                        value.getConversationId(),
                        conversationId
                ))
                .filter(value -> operationId.equals(value.getOperationId()))
                .orElseThrow(AiQueryTransactionService::taskNotFound);
        ConversationMessage assistant = messageRepository
                .findByConversationIdAndTurnIdAndRole(
                        conversationId,
                        operationId,
                        MessageRole.ASSISTANT
                )
                .orElse(null);
        return new AiQueryResult(
                assistant == null ? null : MessageView.from(assistant),
                TaskView.from(task)
        );
    }

    private LockedState lockState(AiExecution expected) {
        Conversation conversation = lockConversation(
                expected.conversationId(),
                expected.ownerId()
        );
        BizTask task = lockTask(
                expected.taskId(),
                expected.ownerId(),
                expected.conversationId(),
                expected.operationId()
        );
        return new LockedState(
                conversation,
                task,
                userMessage(expected.conversationId(), expected.operationId())
        );
    }

    private Conversation lockConversation(
            Long conversationId,
            Long ownerId
    ) {
        return conversationRepository.findByIdForUpdate(conversationId)
                .filter(value -> ownerId.equals(value.getOwnerId()))
                .orElseThrow(AiQueryTransactionService::conversationNotFound);
    }

    private BizTask lockTask(
            Long taskId,
            Long ownerId,
            Long conversationId,
            String operationId
    ) {
        return taskRepository.findByIdForUpdate(taskId)
                .filter(value -> ownerId.equals(value.getOwnerId()))
                .filter(value -> conversationId.equals(value.getConversationId()))
                .filter(value -> operationId.equals(value.getOperationId()))
                .filter(value -> value.getType() == TaskType.AI_QUERY)
                .orElseThrow(AiQueryTransactionService::taskNotFound);
    }

    private ConversationMessage userMessage(Long conversationId, String operationId) {
        return messageRepository.findByTurnForReplay(
                        conversationId,
                        operationId,
                        MessageRole.USER
                )
                .orElseThrow(() -> new IllegalStateException(
                        "AI query task is missing its user message"
                ));
    }

    private AiExecution execution(
            Conversation conversation,
            BizTask task,
            ConversationMessage userMessage
    ) {
        return new AiExecution(
                task.getId(),
                task.getOwnerId(),
                task.getConversationId(),
                task.getOperationId(),
                task.getRequestHash(),
                task.getVersion(),
                conversation.getContextVersion(),
                userMessage.getRequestId(),
                task.getStatus()
        );
    }

    private static AiChatRequest.HistoryItem historyItem(
            ConversationMessage message
    ) {
        return new AiChatRequest.HistoryItem(
                String.valueOf(message.getId()),
                AiChatRequest.Role.valueOf(message.getRole().name()),
                message.getContent(),
                message.getCreatedAt()
        );
    }

    private List<AiChatRequest.HistoryItem> history(
            Long conversationId,
            String operationId
    ) {
        List<ConversationMessage> descending = messageRepository
                .findRecentExcludingTurn(
                        conversationId,
                        operationId,
                        MessageStatus.COMPLETED,
                        PageRequest.of(0, 20)
                );
        List<ConversationMessage> ascending = new ArrayList<>(descending);
        Collections.reverse(ascending);
        return ascending.stream()
                .map(AiQueryTransactionService::historyItem)
                .toList();
    }

    private void validateResult(AiExecution expected, AiChatResponse response) {
        if (response == null
                || !expected.originalRequestId().equals(response.requestId())
                || !expected.operationId().equals(response.operationId())
                || response.contextVersion() != expected.contextVersion() + 1
                || response.nextContext() == null) {
            throw conflict(
                    "AI_PROTOCOL_ERROR",
                    "The AI result does not match the durable operation"
            );
        }
    }

    private Map<String, Object> resultMetadata(
            AiChatResponse response,
            String resultFingerprint
    ) {
        LinkedHashMap<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("resultFingerprint", resultFingerprint);
        metadata.put("runId", response.runId());
        metadata.put("traceId", response.traceId());
        metadata.put("outcome", response.outcome().name());
        metadata.put("followUpQuestions", response.followUpQuestions());
        metadata.put("toolsUsed", response.toolsUsed());
        metadata.put("sources", objectMapper.convertValue(response.sources(), SOURCE_LIST));
        LinkedHashMap<String, Object> safety = new LinkedHashMap<>();
        safety.put("decision", response.safety().decision().name());
        safety.put("reasonCode", response.safety().reasonCode());
        metadata.put("safety", safety);
        return metadata;
    }

    private String fingerprint(AiChatResponse response) {
        try {
            byte[] serialized = objectMapper.writeValueAsString(response)
                    .getBytes(StandardCharsets.UTF_8);
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(serialized)
            );
        } catch (JsonProcessingException | NoSuchAlgorithmException exception) {
            throw new IllegalStateException("AI result fingerprint failed", exception);
        }
    }

    private void registerContextWriteAfterCommit(
            Long ownerId,
            Long conversationId,
            long contextVersion,
            com.fasterxml.jackson.databind.JsonNode context
    ) {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        contextStore.put(
                                ownerId,
                                conversationId,
                                contextVersion,
                                context
                        );
                    }
                }
        );
    }

    private void appendAudit(
            Long ownerId,
            String action,
            BizTask task,
            AuditRequestMetadata metadata,
            Map<String, ?> details
    ) {
        auditService.append(new AuditEvent(
                ownerId,
                action,
                "TASK",
                String.valueOf(task.getId()),
                RequestIds.current(),
                "SUCCESS",
                metadata.clientIp(),
                metadata.userAgent(),
                details
        ));
    }

    private static void requireExpectedVersion(
            BizTask task,
            AiExecution expected
    ) {
        if (task.getVersion() != expected.taskVersion()) {
            throw conflict("TASK_VERSION_CONFLICT", "The AI task version changed");
        }
    }

    private static void requireActiveOperation(
            Conversation conversation,
            String operationId
    ) {
        if (!Objects.equals(conversation.getActiveOperationId(), operationId)) {
            throw conflict(
                    "CONVERSATION_STATE_CONFLICT",
                    "The conversation active operation changed"
            );
        }
    }

    private static boolean isTerminal(TaskStatus status) {
        return status == TaskStatus.SUCCEEDED
                || status == TaskStatus.FAILED
                || status == TaskStatus.TIMED_OUT
                || status == TaskStatus.CANCELLED;
    }

    private AiQueryResult currentResult(
            Conversation conversation,
            BizTask task
    ) {
        ConversationMessage assistant = messageRepository
                .findByConversationIdAndTurnIdAndRole(
                        conversation.getId(),
                        task.getOperationId(),
                        MessageRole.ASSISTANT
                )
                .orElse(null);
        return new AiQueryResult(
                assistant == null ? null : MessageView.from(assistant),
                TaskView.from(task)
        );
    }

    private static String boundedErrorCode(String errorCode) {
        String value = errorCode == null || errorCode.isBlank()
                ? "AI_SERVICE_UNAVAILABLE"
                : errorCode;
        return value.length() <= 128 ? value : value.substring(0, 128);
    }

    private static ApiException conversationNotFound() {
        return new ApiException(
                HttpStatus.NOT_FOUND,
                "CONVERSATION_NOT_FOUND",
                "The conversation was not found"
        );
    }

    private static ApiException taskNotFound() {
        return new ApiException(
                HttpStatus.NOT_FOUND,
                "TASK_NOT_FOUND",
                "The task was not found"
        );
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message);
    }

    public record AiExecution(
            Long taskId,
            Long ownerId,
            Long conversationId,
            String operationId,
            String requestHash,
            long taskVersion,
            long contextVersion,
            String originalRequestId,
            TaskStatus taskStatus
    ) {
    }

    public record PreparedAiQuery(
            AiExecution execution,
            String query,
            List<AiChatRequest.HistoryItem> history,
            boolean submitRequired
    ) {

        public PreparedAiQuery {
            history = List.copyOf(history);
        }
    }

    public record AiQueryResult(
            MessageView assistantMessage,
            TaskView task
    ) {
    }

    private record LockedState(
            Conversation conversation,
            BizTask task,
            ConversationMessage userMessage
    ) {
    }
}
