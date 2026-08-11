package com.livestock.platform.conversation.service;

import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.ai.context.RedisAiContextStore;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.conversation.api.ConversationDetailResponse;
import com.livestock.platform.conversation.api.ConversationListResponse;
import com.livestock.platform.conversation.api.ConversationView;
import com.livestock.platform.conversation.api.CreateConversationRequest;
import com.livestock.platform.conversation.api.MessageView;
import com.livestock.platform.conversation.api.UpdateConversationRequest;
import com.livestock.platform.conversation.domain.Conversation;
import com.livestock.platform.conversation.domain.ConversationMessage;
import com.livestock.platform.conversation.domain.ConversationStatus;
import com.livestock.platform.conversation.repository.ConversationMessageRepository;
import com.livestock.platform.conversation.repository.ConversationRepository;
import com.livestock.platform.security.UserPrincipal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ConversationService {

    private static final int DETAIL_MESSAGE_LIMIT = 100;
    private static final String DEFAULT_TITLE = "New conversation";

    private final ConversationRepository conversationRepository;
    private final ConversationMessageRepository messageRepository;
    private final AuditService auditService;
    private final RedisAiContextStore contextStore;

    public ConversationService(
            ConversationRepository conversationRepository,
            ConversationMessageRepository messageRepository,
            AuditService auditService,
            RedisAiContextStore contextStore
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.auditService = auditService;
        this.contextStore = contextStore;
    }

    @Transactional
    public ConversationView create(
            CreateConversationRequest request,
            UserPrincipal actor,
            AuditRequestMetadata metadata
    ) {
        Long ownerId = actorId(actor);
        String title = request.title() == null || request.title().isBlank()
                ? DEFAULT_TITLE
                : request.title().trim();
        Conversation conversation = conversationRepository.saveAndFlush(
                new Conversation(ownerId, title)
        );
        appendAudit(
                actor,
                "CONVERSATION_CREATED",
                conversation,
                metadata,
                Map.of("status", conversation.getStatus())
        );
        return ConversationView.from(conversation);
    }

    @Transactional(readOnly = true)
    public ConversationListResponse list(
            String scope,
            int page,
            int size,
            UserPrincipal actor
    ) {
        boolean readAll = "all".equalsIgnoreCase(scope);
        if (!readAll && !"own".equalsIgnoreCase(scope)) {
            throw new ApiException(
                    HttpStatus.BAD_REQUEST,
                    "INVALID_SCOPE",
                    "Scope must be own or all"
            );
        }
        PageRequest request = PageRequest.of(
                page,
                size,
                Sort.by(Sort.Order.desc("updatedAt"), Sort.Order.desc("id"))
        );
        Page<Conversation> conversations;
        if (readAll) {
            requireAuthority(actor, "CONVERSATION_READ_ALL");
            conversations = conversationRepository.findAllByStatusNot(
                    ConversationStatus.DELETED,
                    request
            );
        } else {
            conversations = conversationRepository.findAllByOwnerIdAndStatusNot(
                    actorId(actor),
                    ConversationStatus.DELETED,
                    request
            );
        }
        return new ConversationListResponse(
                conversations.getContent().stream()
                        .map(ConversationView::from)
                        .toList(),
                conversations.getNumber(),
                conversations.getSize(),
                conversations.getTotalElements(),
                conversations.getTotalPages()
        );
    }

    @Transactional(readOnly = true)
    public ConversationDetailResponse get(Long id, UserPrincipal actor) {
        Conversation conversation = findReadable(id, actor);
        List<ConversationMessage> descending = messageRepository
                .findByConversationIdOrderByCreatedAtDescIdDesc(
                        conversation.getId(),
                        PageRequest.of(0, DETAIL_MESSAGE_LIMIT)
                )
                .getContent();
        List<ConversationMessage> ascending = new ArrayList<>(descending);
        java.util.Collections.reverse(ascending);
        return new ConversationDetailResponse(
                ConversationView.from(conversation),
                ascending.stream().map(MessageView::from).toList()
        );
    }

    @Transactional(readOnly = true)
    public List<MessageView> boundedHistory(
            Long id,
            int limit,
            UserPrincipal actor
    ) {
        Conversation conversation = findReadable(id, actor);
        int boundedLimit = Math.max(1, Math.min(limit, 20));
        List<ConversationMessage> descending = messageRepository
                .findByConversationIdOrderByCreatedAtDescIdDesc(
                        conversation.getId(),
                        PageRequest.of(0, boundedLimit)
                )
                .getContent();
        List<ConversationMessage> ascending = new ArrayList<>(descending);
        java.util.Collections.reverse(ascending);
        return ascending.stream().map(MessageView::from).toList();
    }

    @Transactional
    public ConversationView update(
            Long id,
            UpdateConversationRequest request,
            UserPrincipal actor,
            AuditRequestMetadata metadata
    ) {
        Conversation conversation = findOwned(id, actorId(actor));
        requireVersion(conversation, request.version());
        boolean hasTitle = request.title() != null;
        boolean hasStatus = request.status() != null;
        if (hasTitle == hasStatus) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    "CONVERSATION_UPDATE_INVALID",
                    "Exactly one of title or status must be supplied"
            );
        }

        String action;
        Map<String, ?> details;
        if (hasTitle) {
            if (request.title().isBlank()) {
                throw new ApiException(
                        HttpStatus.UNPROCESSABLE_ENTITY,
                        "CONVERSATION_TITLE_INVALID",
                        "Conversation title must not be blank"
                );
            }
            String nextTitle = request.title().trim();
            String previousTitle = conversation.getTitle();
            if (previousTitle.equals(nextTitle)) {
                return ConversationView.from(conversation);
            }
            conversation.rename(nextTitle);
            action = "CONVERSATION_RENAMED";
            details = Map.of(
                    "previousTitleLength",
                    previousTitle.length(),
                    "titleLength",
                    conversation.getTitle().length()
            );
        } else {
            ConversationStatus previousStatus = conversation.getStatus();
            if (previousStatus == request.status()) {
                return ConversationView.from(conversation);
            }
            requireStatusTransition(conversation, request.status());
            conversation.changeStatus(request.status());
            action = request.status() == ConversationStatus.ARCHIVED
                    ? "CONVERSATION_ARCHIVED"
                    : "CONVERSATION_REOPENED";
            details = Map.of("from", previousStatus, "to", request.status());
            if (request.status() == ConversationStatus.ARCHIVED) {
                registerContextDeleteAfterCommit(
                        conversation.getOwnerId(),
                        conversation.getId()
                );
            }
        }
        conversationRepository.saveAndFlush(conversation);
        appendAudit(actor, action, conversation, metadata, details);
        return ConversationView.from(conversation);
    }

    @Transactional
    public void delete(
            Long id,
            long expectedVersion,
            UserPrincipal actor,
            AuditRequestMetadata metadata
    ) {
        Conversation conversation = findOwned(id, actorId(actor));
        requireVersion(conversation, expectedVersion);
        if (conversation.getActiveOperationId() != null) {
            throw conflict(
                    "CONVERSATION_BUSY",
                    "The conversation has an active operation"
            );
        }
        ConversationStatus previous = conversation.getStatus();
        conversation.changeStatus(ConversationStatus.DELETED);
        conversationRepository.saveAndFlush(conversation);
        appendAudit(
                actor,
                "CONVERSATION_DELETED",
                conversation,
                metadata,
                Map.of("from", previous, "to", ConversationStatus.DELETED)
        );
        registerContextDeleteAfterCommit(
                conversation.getOwnerId(),
                conversation.getId()
        );
    }

    private Conversation findReadable(Long id, UserPrincipal actor) {
        if (actor.authorities().contains("CONVERSATION_READ_ALL")) {
            return conversationRepository.findById(id)
                    .filter(value -> value.getStatus() != ConversationStatus.DELETED)
                    .orElseThrow(ConversationService::notFound);
        }
        return conversationRepository.findByIdAndOwnerIdAndStatusNot(
                        id,
                        actorId(actor),
                        ConversationStatus.DELETED
                )
                .orElseThrow(ConversationService::notFound);
    }

    private Conversation findOwned(Long id, Long ownerId) {
        return conversationRepository.findByIdAndOwnerIdAndStatusNot(
                        id,
                        ownerId,
                        ConversationStatus.DELETED
                )
                .orElseThrow(ConversationService::notFound);
    }

    private static void requireStatusTransition(
            Conversation conversation,
            ConversationStatus next
    ) {
        if (next == ConversationStatus.DELETED) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    "CONVERSATION_STATUS_INVALID",
                    "Use DELETE to delete a conversation"
            );
        }
        if (conversation.getActiveOperationId() != null) {
            throw conflict(
                    "CONVERSATION_BUSY",
                    "The conversation has an active operation"
            );
        }
        ConversationStatus current = conversation.getStatus();
        boolean valid = current == next
                || current == ConversationStatus.ACTIVE
                && next == ConversationStatus.ARCHIVED
                || current == ConversationStatus.ARCHIVED
                && next == ConversationStatus.ACTIVE;
        if (!valid) {
            throw conflict(
                    "CONVERSATION_STATUS_CONFLICT",
                    "The conversation status transition is not allowed"
            );
        }
    }

    private void appendAudit(
            UserPrincipal actor,
            String action,
            Conversation conversation,
            AuditRequestMetadata metadata,
            Map<String, ?> details
    ) {
        auditService.append(new AuditEvent(
                actorId(actor),
                action,
                "CONVERSATION",
                String.valueOf(conversation.getId()),
                RequestIds.current(),
                "SUCCESS",
                metadata.clientIp(),
                metadata.userAgent(),
                details
        ));
    }

    private void registerContextDeleteAfterCommit(Long ownerId, Long conversationId) {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        contextStore.delete(ownerId, conversationId);
                    }
                }
        );
    }

    private static void requireVersion(Conversation conversation, long expectedVersion) {
        if (conversation.getVersion() != expectedVersion) {
            throw conflict(
                    "VERSION_CONFLICT",
                    "The conversation changed before this request completed"
            );
        }
    }

    private static void requireAuthority(UserPrincipal actor, String authority) {
        if (!actor.authorities().contains(authority)) {
            throw new AccessDeniedException("Access is denied");
        }
    }

    private static Long actorId(UserPrincipal actor) {
        return Long.valueOf(actor.userId());
    }

    private static ApiException notFound() {
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
