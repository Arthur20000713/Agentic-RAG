package com.livestock.platform.ai;

record AiServiceErrorResponse(
        String requestId,
        String operationId,
        AiErrorDetail error
) {
}
