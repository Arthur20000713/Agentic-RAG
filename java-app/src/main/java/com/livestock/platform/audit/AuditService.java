package com.livestock.platform.audit;

import com.livestock.platform.audit.repository.AuditLogRepository;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;

@Service
public class AuditService {

    private static final int ACTION_LENGTH = 64;
    private static final int RESOURCE_TYPE_LENGTH = 64;
    private static final int RESOURCE_ID_LENGTH = 128;
    private static final int REQUEST_ID_LENGTH = 128;
    private static final int RESULT_LENGTH = 16;
    private static final int CLIENT_IP_LENGTH = 45;
    private static final int USER_AGENT_LENGTH = 512;

    private final AuditLogRepository auditLogRepository;
    private final AuditSanitizer auditSanitizer;

    public AuditService(
            AuditLogRepository auditLogRepository,
            AuditSanitizer auditSanitizer
    ) {
        this.auditLogRepository = auditLogRepository;
        this.auditSanitizer = auditSanitizer;
    }

    @Transactional
    public AuditLog append(AuditEvent event) {
        return appendInternal(event);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public AuditLog appendInNewTransaction(AuditEvent event) {
        return appendInternal(event);
    }

    private AuditLog appendInternal(AuditEvent event) {
        Map<String, Object> details = auditSanitizer.sanitize(event.details());
        AuditLog auditLog = new AuditLog(
                event.actorId(),
                requireSafeBounded(event.action(), ACTION_LENGTH, "action"),
                requireSafeBounded(
                        event.resourceType(),
                        RESOURCE_TYPE_LENGTH,
                        "resourceType"
                ),
                safeBounded(event.resourceId(), RESOURCE_ID_LENGTH),
                requireSafeBounded(event.requestId(), REQUEST_ID_LENGTH, "requestId"),
                requireSafeBounded(event.result(), RESULT_LENGTH, "result"),
                safeBounded(event.clientIp(), CLIENT_IP_LENGTH),
                safeBounded(event.userAgent(), USER_AGENT_LENGTH),
                details
        );
        return auditLogRepository.append(auditLog);
    }

    private String requireSafeBounded(
            String value,
            int maximumLength,
            String fieldName
    ) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " must not be blank");
        }
        return safeBounded(value, maximumLength);
    }

    private String safeBounded(String value, int maximumLength) {
        String sanitized = auditSanitizer.sanitizeText(value);
        if (sanitized == null || sanitized.length() <= maximumLength) {
            return sanitized;
        }
        return sanitized.substring(0, maximumLength);
    }
}
