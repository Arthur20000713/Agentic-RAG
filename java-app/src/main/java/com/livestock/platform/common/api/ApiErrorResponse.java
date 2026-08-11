package com.livestock.platform.common.api;

import java.time.Instant;

public record ApiErrorResponse(
        String requestId,
        ErrorDetail error,
        Instant timestamp
) {
    public static ApiErrorResponse of(String requestId, String code, String message) {
        return new ApiErrorResponse(
                requestId,
                new ErrorDetail(code, message),
                Instant.now()
        );
    }

    public record ErrorDetail(String code, String message) {
    }
}
