package com.livestock.platform.task.domain;

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
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;
import org.hibernate.annotations.CreationTimestamp;

@Entity
@Table(name = "biz_task")
public class BizTask {

    private static final Set<TaskStatus> TERMINAL_STATUSES = EnumSet.of(
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.TIMED_OUT,
            TaskStatus.CANCELLED
    );

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_id", nullable = false)
    private Long ownerId;

    @Column(name = "conversation_id")
    private Long conversationId;

    @Enumerated(EnumType.STRING)
    @Column(name = "type", nullable = false, length = 32)
    private TaskType type;

    @Column(name = "operation_id", nullable = false, length = 128)
    private String operationId;

    @Column(name = "request_hash", nullable = false, length = 64)
    private String requestHash;

    @Column(name = "executor_job_id", length = 128)
    private String executorJobId;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 32)
    private TaskStatus status;

    @Column(name = "progress", nullable = false)
    private int progress;

    @Column(name = "result_ref", length = 512)
    private String resultRef;

    @Column(name = "error_code", length = 128)
    private String errorCode;

    @Column(name = "retry_count", nullable = false)
    private int retryCount;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "started_at")
    private Instant startedAt;

    @Column(name = "finished_at")
    private Instant finishedAt;

    protected BizTask() {
    }

    public BizTask(
            Long ownerId,
            Long conversationId,
            TaskType type,
            String operationId,
            String requestHash
    ) {
        this.ownerId = Objects.requireNonNull(ownerId, "ownerId");
        this.conversationId = conversationId;
        this.type = Objects.requireNonNull(type, "type");
        this.operationId = requireText(operationId, 128, "operationId");
        this.requestHash = requireText(requestHash, 64, "requestHash");
        this.status = TaskStatus.CREATED;
    }

    public void applyTransition(
            TaskStatus nextStatus,
            int nextProgress,
            String nextResultRef,
            String nextErrorCode,
            Instant now
    ) {
        TaskStatus requiredStatus = Objects.requireNonNull(nextStatus, "nextStatus");
        Instant requiredNow = Objects.requireNonNull(now, "now");
        if (nextProgress < 0 || nextProgress > 100) {
            throw new IllegalArgumentException("progress must be between 0 and 100");
        }
        status = requiredStatus;
        progress = nextProgress;
        resultRef = optionalText(nextResultRef, 512, "resultRef");
        errorCode = optionalText(nextErrorCode, 128, "errorCode");
        if (requiredStatus == TaskStatus.RUNNING && startedAt == null) {
            startedAt = requiredNow;
        }
        if (TERMINAL_STATUSES.contains(requiredStatus)) {
            finishedAt = requiredNow;
        }
    }

    public void setExecutorJobId(String nextExecutorJobId) {
        executorJobId = optionalText(nextExecutorJobId, 128, "executorJobId");
    }

    public void incrementRetryCount() {
        retryCount++;
    }

    private static String requireText(
            String value,
            int maximumLength,
            String fieldName
    ) {
        if (value == null || value.isBlank() || value.length() > maximumLength) {
            throw new IllegalArgumentException(fieldName + " is invalid");
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

    public Long getOwnerId() {
        return ownerId;
    }

    public Long getConversationId() {
        return conversationId;
    }

    public TaskType getType() {
        return type;
    }

    public String getOperationId() {
        return operationId;
    }

    public String getRequestHash() {
        return requestHash;
    }

    public String getExecutorJobId() {
        return executorJobId;
    }

    public TaskStatus getStatus() {
        return status;
    }

    public int getProgress() {
        return progress;
    }

    public String getResultRef() {
        return resultRef;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public int getRetryCount() {
        return retryCount;
    }

    public long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getStartedAt() {
        return startedAt;
    }

    public Instant getFinishedAt() {
        return finishedAt;
    }
}
