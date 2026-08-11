package com.livestock.platform.conversation.api;

import com.livestock.platform.conversation.domain.ConversationStatus;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record UpdateConversationRequest(
        @Size(max = 120) String title,
        ConversationStatus status,
        @NotNull @Min(0) Long version
) {
}
