package com.livestock.platform.conversation.repository;

import com.livestock.platform.conversation.domain.ConversationMessage;
import com.livestock.platform.conversation.domain.MessageRole;
import com.livestock.platform.conversation.domain.MessageStatus;
import java.util.List;
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ConversationMessageRepository
        extends JpaRepository<ConversationMessage, Long> {

    Page<ConversationMessage> findByConversationIdOrderByCreatedAtDescIdDesc(
            Long conversationId,
            Pageable pageable
    );

    Optional<ConversationMessage> findByConversationIdAndTurnIdAndRole(
            Long conversationId,
            String turnId,
            MessageRole role
    );

    @Lock(LockModeType.PESSIMISTIC_READ)
    @Query("""
            select message
            from ConversationMessage message
            where message.conversationId = :conversationId
              and message.turnId = :turnId
              and message.role = :role
            """)
    Optional<ConversationMessage> findByTurnForReplay(
            @Param("conversationId") Long conversationId,
            @Param("turnId") String turnId,
            @Param("role") MessageRole role
    );

    @Query("""
            select message
            from ConversationMessage message
            where message.conversationId = :conversationId
              and message.status = :status
              and message.turnId <> :excludedTurnId
            order by message.createdAt desc, message.id desc
            """)
    List<ConversationMessage> findRecentExcludingTurn(
            @Param("conversationId") Long conversationId,
            @Param("excludedTurnId") String excludedTurnId,
            @Param("status") MessageStatus status,
            Pageable pageable
    );

}
