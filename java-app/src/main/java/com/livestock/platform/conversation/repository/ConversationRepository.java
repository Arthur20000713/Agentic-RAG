package com.livestock.platform.conversation.repository;

import com.livestock.platform.conversation.domain.Conversation;
import com.livestock.platform.conversation.domain.ConversationStatus;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationRepository extends JpaRepository<Conversation, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select conversation from Conversation conversation where conversation.id = :id")
    Optional<Conversation> findByIdForUpdate(@Param("id") Long id);

    Optional<Conversation> findByIdAndOwnerId(Long id, Long ownerId);

    Optional<Conversation> findByIdAndOwnerIdAndStatusNot(
            Long id,
            Long ownerId,
            ConversationStatus excludedStatus
    );

    boolean existsByIdAndOwnerIdAndStatusNot(
            Long id,
            Long ownerId,
            ConversationStatus excludedStatus
    );

    Optional<Conversation> findByIdAndActiveOperationId(
            Long id,
            String activeOperationId
    );

    Page<Conversation> findAllByOwnerId(Long ownerId, Pageable pageable);

    Page<Conversation> findAllByOwnerIdAndStatusNot(
            Long ownerId,
            ConversationStatus excludedStatus,
            Pageable pageable
    );

    Page<Conversation> findAllByStatusNot(
            ConversationStatus excludedStatus,
            Pageable pageable
    );

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query(
            value = """
                    UPDATE conversation
                    SET active_operation_id = :operationId,
                        last_message_at = CURRENT_TIMESTAMP(6),
                        version = version + 1,
                        updated_at = CURRENT_TIMESTAMP(6)
                    WHERE id = :id
                      AND owner_id = :ownerId
                      AND status = 'ACTIVE'
                      AND active_operation_id IS NULL
                      AND context_version = :expectedContextVersion
                    """,
            nativeQuery = true
    )
    int claimOperation(
            @Param("id") Long id,
            @Param("ownerId") Long ownerId,
            @Param("operationId") String operationId,
            @Param("expectedContextVersion") long expectedContextVersion
    );
}
