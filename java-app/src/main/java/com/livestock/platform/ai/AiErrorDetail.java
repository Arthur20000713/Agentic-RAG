package com.livestock.platform.ai;

import com.fasterxml.jackson.databind.JsonNode;

public record AiErrorDetail(
        String code,
        String message,
        boolean retryable,
        JsonNode details
) {
}
