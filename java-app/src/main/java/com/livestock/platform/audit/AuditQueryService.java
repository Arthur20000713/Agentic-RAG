package com.livestock.platform.audit;

import com.livestock.platform.audit.api.AuditLogListResponse;
import com.livestock.platform.audit.api.AuditLogView;
import jakarta.persistence.EntityManager;
import jakarta.persistence.TypedQuery;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditQueryService {

    private final EntityManager entityManager;
    private final AuditSanitizer auditSanitizer;

    public AuditQueryService(
            EntityManager entityManager,
            AuditSanitizer auditSanitizer
    ) {
        this.entityManager = entityManager;
        this.auditSanitizer = auditSanitizer;
    }

    @Transactional(readOnly = true)
    public AuditLogListResponse find(String requestId, int page, int size) {
        String where = requestId == null || requestId.isBlank()
                ? ""
                : " where log.requestId = :requestId";
        TypedQuery<AuditLog> query = entityManager.createQuery(
                "select log from AuditLog log"
                        + where
                        + " order by log.createdAt desc, log.id desc",
                AuditLog.class
        );
        TypedQuery<Long> countQuery = entityManager.createQuery(
                "select count(log.id) from AuditLog log" + where,
                Long.class
        );
        if (!where.isEmpty()) {
            query.setParameter("requestId", requestId);
            countQuery.setParameter("requestId", requestId);
        }
        List<AuditLogView> items = query
                .setFirstResult(page * size)
                .setMaxResults(size)
                .getResultList()
                .stream()
                .map(log -> AuditLogView.from(log, auditSanitizer))
                .toList();
        long total = countQuery.getSingleResult();
        int totalPages = total == 0 ? 0 : (int) ((total + size - 1) / size);
        return new AuditLogListResponse(items, page, size, total, totalPages);
    }
}
