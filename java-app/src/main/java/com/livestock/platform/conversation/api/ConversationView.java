package com.livestock.platform.conversation.api;

import com.livestock.platform.conversation.domain.Conversation;
import com.livestock.platform.conversation.domain.ConversationStatus;
import java.time.Instant;

public record ConversationView(
        String id,
        String ownerId,
        String title,
        ConversationStatus status,
        long contextVersion,
        long version,
        Instant createdAt,
        Instant updatedAt,
        Instant lastMessageAt
) {
    public static ConversationView from(Conversation conversation) {
        return new ConversationView(
                String.valueOf(conversation.getId()),
                String.valueOf(conversation.getOwnerId()),
                conversation.getTitle(),
                conversation.getStatus(),
                conversation.getContextVersion(),
                conversation.getVersion(),
                conversation.getCreatedAt(),
                conversation.getUpdatedAt(),
                conversation.getLastMessageAt()
        );
    }
}
