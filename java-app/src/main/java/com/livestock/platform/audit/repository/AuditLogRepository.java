package com.livestock.platform.audit.repository;

import com.livestock.platform.audit.AuditLog;

public interface AuditLogRepository {

    AuditLog append(AuditLog auditLog);
}
