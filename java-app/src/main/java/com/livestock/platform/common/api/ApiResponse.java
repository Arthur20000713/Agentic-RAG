package com.livestock.platform.common.api;

import java.time.Instant;

public record ApiResponse<T>(
        String requestId,
        T data,
        Instant timestamp
) {
    public static <T> ApiResponse<T> success(String requestId, T data) {
        return new ApiResponse<>(requestId, data, Instant.now());
    }
}
