package com.livestock.platform.audit;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

public record AuditEvent(
        Long actorId,
        String action,
        String resourceType,
        String resourceId,
        String requestId,
        String result,
        String clientIp,
        String userAgent,
        Map<String, ?> details
) {
    public AuditEvent {
        Objects.requireNonNull(action, "action");
        Objects.requireNonNull(resourceType, "resourceType");
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(result, "result");
        details = details == null
                ? Collections.emptyMap()
                : Collections.unmodifiableMap(new LinkedHashMap<>(details));
    }
}
