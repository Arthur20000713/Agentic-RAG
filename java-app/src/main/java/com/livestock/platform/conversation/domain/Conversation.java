package com.livestock.platform.conversation.domain;

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
@Table(name = "conversation")
public class Conversation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_id", nullable = false)
    private Long ownerId;

    @Column(name = "title", nullable = false, length = 255)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 16)
    private ConversationStatus status;

    @Column(name = "context_version", nullable = false)
    private long contextVersion;

    @Column(name = "active_operation_id", length = 128)
    private String activeOperationId;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "last_message_at")
    private Instant lastMessageAt;

    protected Conversation() {
    }

    public Conversation(Long ownerId, String title) {
        this.ownerId = Objects.requireNonNull(ownerId, "ownerId");
        this.title = requireText(title, 255, "title");
        this.status = ConversationStatus.ACTIVE;
    }

    public void rename(String nextTitle) {
        title = requireText(nextTitle, 255, "title");
    }

    public void changeStatus(ConversationStatus nextStatus) {
        status = Objects.requireNonNull(nextStatus, "nextStatus");
    }

    public void releaseOperation(String expectedOperationId) {
        requireActiveOperation(expectedOperationId);
        activeOperationId = null;
    }

    public void completeOperation(String expectedOperationId, Instant messageAt) {
        requireActiveOperation(expectedOperationId);
        contextVersion++;
        activeOperationId = null;
        lastMessageAt = Objects.requireNonNull(messageAt, "messageAt");
    }

    private void requireActiveOperation(String expectedOperationId) {
        if (!Objects.equals(activeOperationId, expectedOperationId)) {
            throw new IllegalStateException("Conversation active operation changed");
        }
    }

    private static String requireText(String value, int maximumLength, String fieldName) {
        if (value == null || value.isBlank() || value.length() > maximumLength) {
            throw new IllegalArgumentException(fieldName + " is invalid");
        }
        return value;
    }

    public Long getId() {
        return id;
    }

    public Long getOwnerId() {
        return ownerId;
    }

    public String getTitle() {
        return title;
    }

    public ConversationStatus getStatus() {
        return status;
    }

    public long getContextVersion() {
        return contextVersion;
    }

    public String getActiveOperationId() {
        return activeOperationId;
    }

    public long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public Instant getLastMessageAt() {
        return lastMessageAt;
    }
}
