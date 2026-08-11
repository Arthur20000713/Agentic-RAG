package com.livestock.platform.conversation.api;

import jakarta.validation.constraints.Size;

public record CreateConversationRequest(
        @Size(max = 120) String title
) {
}
