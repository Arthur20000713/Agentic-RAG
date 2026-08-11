package com.livestock.platform.conversation.api;

import java.util.List;

public record ConversationListResponse(
        List<ConversationView> items,
        int page,
        int size,
        long totalElements,
        int totalPages
) {
}
