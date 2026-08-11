package com.livestock.platform.conversation.api;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record SubmitMessageRequest(
        @NotBlank @Size(max = 4000) String content,
        @NotNull @Min(0) Long contextVersion
) {
}
