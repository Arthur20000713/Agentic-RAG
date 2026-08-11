package com.livestock.platform.audit.api;

import java.util.List;

public record AuditLogListResponse(
        List<AuditLogView> items,
        int page,
        int size,
        long totalElements,
        int totalPages
) {
}
