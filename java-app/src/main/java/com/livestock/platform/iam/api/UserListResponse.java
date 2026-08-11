package com.livestock.platform.iam.api;

import java.util.List;

public record UserListResponse(
        List<UserView> items,
        int page,
        int size,
        long totalElements,
        int totalPages
) {
}
