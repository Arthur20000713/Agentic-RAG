package com.livestock.platform.conversation.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "conversation_message")
public class ConversationMessage {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "conversation_id", nullable = false)
    private Long conversationId;

    @Column(name = "turn_id", nullable = false, length = 128)
    private String turnId;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false, length = 16)
    private MessageRole role;

    @Column(name = "content", nullable = false, columnDefinition = "mediumtext")
    private String content;

    @Column(name = "request_id", nullable = false, length = 128)
    private String requestId;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 16)
    private MessageStatus status;

    @Column(name = "intent", length = 128)
    private String intent;

    @Enumerated(EnumType.STRING)
    @Column(name = "risk_level", length = 16)
    private RiskLevel riskLevel;

    @Enumerated(EnumType.STRING)
    @Column(name = "evidence_status", length = 32)
    private EvidenceStatus evidenceStatus;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "metadata_json", nullable = false, columnDefinition = "json")
    private Map<String, Object> metadata = new LinkedHashMap<>();

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected ConversationMessage() {
    }

    public ConversationMessage(
            Long conversationId,
            String turnId,
            MessageRole role,
            String content,
            String requestId,
            MessageStatus status
    ) {
        this(
                conversationId,
                turnId,
                role,
                content,
                requestId,
                status,
                null,
                null,
                null,
                Map.of()
        );
    }

    public ConversationMessage(
            Long conversationId,
            String turnId,
            MessageRole role,
            String content,
            String requestId,
            MessageStatus status,
            String intent,
            RiskLevel riskLevel,
            EvidenceStatus evidenceStatus,
            Map<String, Object> metadata
    ) {
        this.conversationId = Objects.requireNonNull(conversationId, "conversationId");
        this.turnId = requireKey(turnId, "turnId");
        this.role = Objects.requireNonNull(role, "role");
        this.content = requireContent(content);
        this.requestId = requireKey(requestId, "requestId");
        this.status = Objects.requireNonNull(status, "status");
        this.intent = optionalText(intent, 128, "intent");
        this.riskLevel = riskLevel;
        this.evidenceStatus = evidenceStatus;
        this.metadata = new LinkedHashMap<>(
                Objects.requireNonNull(metadata, "metadata")
        );
    }

    private static String requireKey(String value, String fieldName) {
        if (value == null || value.isBlank() || value.length() > 128) {
            throw new IllegalArgumentException(fieldName + " is invalid");
        }
        return value;
    }

    private static String requireContent(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("content must not be blank");
        }
        return value;
    }

    private static String optionalText(
            String value,
            int maximumLength,
            String fieldName
    ) {
        if (value != null && value.length() > maximumLength) {
            throw new IllegalArgumentException(fieldName + " is too long");
        }
        return value;
    }

    public Long getId() {
        return id;
    }

    public Long getConversationId() {
        return conversationId;
    }

    public String getTurnId() {
        return turnId;
    }

    public MessageRole getRole() {
        return role;
    }

    public String getContent() {
        return content;
    }

    public String getRequestId() {
        return requestId;
    }

    public MessageStatus getStatus() {
        return status;
    }

    public String getIntent() {
        return intent;
    }

    public RiskLevel getRiskLevel() {
        return riskLevel;
    }

    public EvidenceStatus getEvidenceStatus() {
        return evidenceStatus;
    }

    public Map<String, Object> getMetadata() {
        return Collections.unmodifiableMap(metadata);
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
