package com.livestock.platform.conversation.service;

import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.conversation.api.MessageSubmissionResponse;
import com.livestock.platform.conversation.api.MessageView;
import com.livestock.platform.conversation.api.SubmitMessageRequest;
import com.livestock.platform.conversation.domain.Conversation;
import com.livestock.platform.conversation.domain.ConversationMessage;
import com.livestock.platform.conversation.domain.ConversationStatus;
import com.livestock.platform.conversation.domain.MessageRole;
import com.livestock.platform.conversation.domain.MessageStatus;
import com.livestock.platform.conversation.repository.ConversationMessageRepository;
import com.livestock.platform.conversation.repository.ConversationRepository;
import com.livestock.platform.iam.repository.UserAccountRepository;
import com.livestock.platform.security.UserPrincipal;
import com.livestock.platform.task.api.TaskView;
import com.livestock.platform.task.domain.BizTask;
import com.livestock.platform.task.domain.TaskType;
import com.livestock.platform.task.repository.BizTaskRepository;
import com.livestock.platform.task.service.IdempotencyHasher;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class MessageSubmissionService {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(MessageSubmissionService.class);

    private final ConversationRepository conversationRepository;
    private final ConversationMessageRepository messageRepository;
    private final BizTaskRepository taskRepository;
    private final UserAccountRepository userAccountRepository;
    private final IdempotencyHasher idempotencyHasher;
    private final AuditService auditService;

    public MessageSubmissionService(
            ConversationRepository conversationRepository,
            ConversationMessageRepository messageRepository,
            BizTaskRepository taskRepository,
            UserAccountRepository userAccountRepository,
            IdempotencyHasher idempotencyHasher,
            AuditService auditService
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.taskRepository = taskRepository;
        this.userAccountRepository = userAccountRepository;
        this.idempotencyHasher = idempotencyHasher;
        this.auditService = auditService;
    }

    @Transactional
    public MessageSubmissionResponse submit(
            Long conversationId,
            String idempotencyKey,
            SubmitMessageRequest request,
            UserPrincipal actor,
            AuditRequestMetadata metadata
    ) {
        Long ownerId = Long.valueOf(actor.userId());
        String requestHash = idempotencyHasher.requestHash(
                conversationId,
                TaskType.AI_QUERY,
                request.contextVersion(),
                request.content()
        );
        if (!conversationRepository.existsByIdAndOwnerIdAndStatusNot(
                conversationId,
                ownerId,
                ConversationStatus.DELETED
        )) {
            throw conversationNotFound();
        }
        BizTask existing = taskRepository
                .findByOwnerIdAndOperationId(ownerId, idempotencyKey)
                .orElse(null);
        if (existing != null) {
            return replay(
                    existing,
                    conversationId,
                    requestHash,
                    idempotencyKey,
                    metadata
            );
        }

        userAccountRepository.findByIdForUpdate(ownerId)
                .orElseThrow(() -> new IllegalStateException(
                        "Authenticated user no longer exists"
                ));
        Conversation conversation = conversationRepository.findByIdForUpdate(conversationId)
                .filter(value -> ownerId.equals(value.getOwnerId()))
                .filter(value -> value.getStatus() != ConversationStatus.DELETED)
                .orElseThrow(MessageSubmissionService::conversationNotFound);

        existing = taskRepository
                .findByOwnerIdAndOperationIdForUpdate(ownerId, idempotencyKey)
                .orElse(null);
        if (existing != null) {
            return replay(
                    existing,
                    conversationId,
                    requestHash,
                    idempotencyKey,
                    metadata
            );
        }
        requireSubmittable(conversation, request.contextVersion());

        int claimed = conversationRepository.claimOperation(
                conversationId,
                ownerId,
                idempotencyKey,
                request.contextVersion()
        );
        if (claimed != 1) {
            throw conflict(
                    "CONVERSATION_BUSY",
                    "The conversation could not be claimed for this operation"
            );
        }

        BizTask task = taskRepository.saveAndFlush(new BizTask(
                ownerId,
                conversationId,
                TaskType.AI_QUERY,
                idempotencyKey,
                requestHash
        ));
        ConversationMessage message = messageRepository.saveAndFlush(
                new ConversationMessage(
                        conversationId,
                        idempotencyKey,
                        MessageRole.USER,
                        request.content(),
                        RequestIds.current(),
                        MessageStatus.COMPLETED
                )
        );
        auditService.append(new AuditEvent(
                ownerId,
                "AI_QUERY_SUBMITTED",
                "TASK",
                String.valueOf(task.getId()),
                RequestIds.current(),
                "SUCCESS",
                metadata.clientIp(),
                metadata.userAgent(),
                Map.of(
                        "conversationId",
                        conversationId,
                        "contextVersion",
                        request.contextVersion(),
                        "idempotencyKeyDigest",
                        idempotencyHasher.keyDigest(idempotencyKey)
                )
        ));
        return response(message, task, false);
    }

    private MessageSubmissionResponse replay(
            BizTask existing,
            Long requestedConversationId,
            String requestHash,
            String idempotencyKey,
            AuditRequestMetadata metadata
    ) {
        if (!requestHash.equals(existing.getRequestHash())
                || !requestedConversationId.equals(existing.getConversationId())) {
            recordRejectedAfterRollback(
                    "IDEMPOTENCY_CONFLICT",
                    existing,
                    idempotencyKey,
                    metadata
            );
            throw conflict(
                    "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was already used for another request"
            );
        }
        ConversationMessage message = messageRepository
                .findByTurnForReplay(
                        requestedConversationId,
                        idempotencyKey,
                        MessageRole.USER
                )
                .orElseThrow(() -> new IllegalStateException(
                        "Idempotent task is missing its user message"
                ));
        return response(message, existing, true);
    }

    private void requireSubmittable(
            Conversation conversation,
            long expectedContextVersion
    ) {
        if (conversation.getStatus() != ConversationStatus.ACTIVE) {
            throw conflict(
                    "CONVERSATION_NOT_ACTIVE",
                    "Messages can only be submitted to an active conversation"
            );
        }
        if (conversation.getContextVersion() != expectedContextVersion) {
            throw conflict(
                    "CONTEXT_VERSION_CONFLICT",
                    "The conversation context version does not match"
            );
        }
        if (conversation.getActiveOperationId() != null) {
            throw conflict(
                    "CONVERSATION_BUSY",
                    "The conversation has an active operation"
            );
        }
    }

    private void recordRejectedAfterRollback(
            String code,
            BizTask task,
            String idempotencyKey,
            AuditRequestMetadata metadata
    ) {
        AuditEvent event = new AuditEvent(
                task.getOwnerId(),
                code,
                "TASK",
                String.valueOf(task.getId()),
                RequestIds.current(),
                "FAILURE",
                metadata.clientIp(),
                metadata.userAgent(),
                Map.of(
                        "errorCode",
                        code,
                        "idempotencyKeyDigest",
                        idempotencyHasher.keyDigest(idempotencyKey)
                )
        );
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCompletion(int status) {
                        if (status != STATUS_ROLLED_BACK) {
                            return;
                        }
                        try {
                            auditService.appendInNewTransaction(event);
                        } catch (RuntimeException exception) {
                            LOGGER.error(
                                    "Failed to append rejected idempotency audit"
                            );
                        }
                    }
                }
        );
    }

    private static MessageSubmissionResponse response(
            ConversationMessage message,
            BizTask task,
            boolean replayed
    ) {
        return new MessageSubmissionResponse(
                MessageView.from(message),
                null,
                TaskView.from(task),
                replayed
        );
    }

    private static ApiException conversationNotFound() {
        return new ApiException(
                HttpStatus.NOT_FOUND,
                "CONVERSATION_NOT_FOUND",
                "The conversation was not found"
        );
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message);
    }
}
