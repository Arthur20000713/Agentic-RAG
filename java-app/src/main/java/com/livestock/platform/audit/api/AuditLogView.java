package com.livestock.platform.audit.api;

import com.livestock.platform.audit.AuditLog;
import com.livestock.platform.audit.AuditSanitizer;
import java.time.Instant;
import java.util.Map;

public record AuditLogView(
        long id,
        String actorId,
        String action,
        String resourceType,
        String resourceId,
        String requestId,
        String result,
        String clientIp,
        String userAgent,
        Map<String, Object> details,
        Instant createdAt
) {
    public static AuditLogView from(
            AuditLog log,
            AuditSanitizer auditSanitizer
    ) {
        return new AuditLogView(
                log.getId(),
                log.getActorId() == null ? null : String.valueOf(log.getActorId()),
                auditSanitizer.sanitizeText(log.getAction()),
                auditSanitizer.sanitizeText(log.getResourceType()),
                auditSanitizer.sanitizeText(log.getResourceId()),
                auditSanitizer.sanitizeText(log.getRequestId()),
                auditSanitizer.sanitizeText(log.getResult()),
                auditSanitizer.sanitizeText(log.getClientIp()),
                auditSanitizer.sanitizeText(log.getUserAgent()),
                auditSanitizer.sanitize(log.getDetails()),
                log.getCreatedAt()
        );
    }
}
