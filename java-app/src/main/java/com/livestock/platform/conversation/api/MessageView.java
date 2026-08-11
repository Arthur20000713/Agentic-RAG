package com.livestock.platform.conversation.api;

import com.livestock.platform.conversation.domain.ConversationMessage;
import com.livestock.platform.conversation.domain.EvidenceStatus;
import com.livestock.platform.conversation.domain.MessageRole;
import com.livestock.platform.conversation.domain.MessageStatus;
import com.livestock.platform.conversation.domain.RiskLevel;
import java.time.Instant;
import java.util.Map;

public record MessageView(
        String id,
        String turnId,
        MessageRole role,
        String content,
        MessageStatus status,
        String intent,
        RiskLevel riskLevel,
        EvidenceStatus evidenceStatus,
        Map<String, Object> metadata,
        Instant createdAt
) {
    public static MessageView from(ConversationMessage message) {
        return new MessageView(
                String.valueOf(message.getId()),
                message.getTurnId(),
                message.getRole(),
                message.getContent(),
                message.getStatus(),
                message.getIntent(),
                message.getRiskLevel(),
                message.getEvidenceStatus(),
                message.getMetadata(),
                message.getCreatedAt()
        );
    }
}
