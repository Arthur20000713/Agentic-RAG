package com.livestock.platform.knowledge.repository;

import com.livestock.platform.knowledge.domain.KnowledgeDocument;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface KnowledgeDocumentRepository extends JpaRepository<KnowledgeDocument, Long> {

    Optional<KnowledgeDocument> findByDocumentIdAndOwnerId(String documentId, Long ownerId);

    Optional<KnowledgeDocument> findByDocumentId(String documentId);

    Optional<KnowledgeDocument> findByOwnerIdAndClientIdempotencyKey(Long ownerId, String key);

    Optional<KnowledgeDocument> findByIndexTaskId(Long taskId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select document from KnowledgeDocument document where document.indexTaskId = :taskId")
    Optional<KnowledgeDocument> findByIndexTaskIdForUpdate(@Param("taskId") Long taskId);
}
