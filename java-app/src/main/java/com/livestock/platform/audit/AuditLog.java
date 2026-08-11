package com.livestock.platform.audit;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@Entity
@Table(name = "audit_log")
public class AuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "actor_id")
    private Long actorId;

    @Column(name = "action", nullable = false, length = 64)
    private String action;

    @Column(name = "resource_type", nullable = false, length = 64)
    private String resourceType;

    @Column(name = "resource_id", length = 128)
    private String resourceId;

    @Column(name = "request_id", nullable = false, length = 128)
    private String requestId;

    @Column(name = "result", nullable = false, length = 16)
    private String result;

    @Column(name = "client_ip", length = 45)
    private String clientIp;

    @Column(name = "user_agent", length = 512)
    private String userAgent;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "detail_json", nullable = false, columnDefinition = "json")
    private Map<String, Object> details;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected AuditLog() {
    }

    public AuditLog(
            Long actorId,
            String action,
            String resourceType,
            String resourceId,
            String requestId,
            String result,
            String clientIp,
            String userAgent,
            Map<String, Object> details
    ) {
        this.actorId = actorId;
        this.action = action;
        this.resourceType = resourceType;
        this.resourceId = resourceId;
        this.requestId = requestId;
        this.result = result;
        this.clientIp = clientIp;
        this.userAgent = userAgent;
        this.details = new LinkedHashMap<>(details);
    }

    public Long getId() {
        return id;
    }

    public Long getActorId() {
        return actorId;
    }

    public String getAction() {
        return action;
    }

    public String getResourceType() {
        return resourceType;
    }

    public String getResourceId() {
        return resourceId;
    }

    public String getRequestId() {
        return requestId;
    }

    public String getResult() {
        return result;
    }

    public String getClientIp() {
        return clientIp;
    }

    public String getUserAgent() {
        return userAgent;
    }

    public Map<String, Object> getDetails() {
        return Collections.unmodifiableMap(details);
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
