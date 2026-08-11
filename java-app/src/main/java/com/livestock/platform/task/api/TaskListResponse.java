package com.livestock.platform.task.api;

import java.util.List;

public record TaskListResponse(
        List<TaskView> items,
        int page,
        int size,
        long totalElements,
        int totalPages
) {
}
