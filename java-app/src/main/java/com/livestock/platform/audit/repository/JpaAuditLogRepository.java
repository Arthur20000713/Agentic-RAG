package com.livestock.platform.audit.repository;

import com.livestock.platform.audit.AuditLog;
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Repository;

@Repository
class JpaAuditLogRepository implements AuditLogRepository {

    private final EntityManager entityManager;

    JpaAuditLogRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public AuditLog append(AuditLog auditLog) {
        entityManager.persist(auditLog);
        return auditLog;
    }
}
