package com.livestock.platform.conversation.api;

import java.util.List;

public record ConversationDetailResponse(
        ConversationView conversation,
        List<MessageView> messages
) {
}
