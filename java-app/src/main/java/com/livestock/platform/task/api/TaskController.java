package com.livestock.platform.task.api;

import com.livestock.platform.common.api.ApiResponse;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.security.UserPrincipal;
import com.livestock.platform.task.service.TaskService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Positive;
import org.springframework.data.domain.Page;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/tasks")
public class TaskController {

    private final TaskService taskService;

    public TaskController(TaskService taskService) {
        this.taskService = taskService;
    }

    @GetMapping
    @PreAuthorize("hasAnyAuthority('TASK_READ_OWN','TASK_MANAGE')")
    public ApiResponse<TaskListResponse> list(
            @RequestParam(defaultValue = "own") String scope,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @AuthenticationPrincipal UserPrincipal actor
    ) {
        Page<TaskView> result = taskService.list(scope, page, size, actor);
        return ApiResponse.success(
                RequestIds.current(),
                new TaskListResponse(
                        result.getContent(),
                        result.getNumber(),
                        result.getSize(),
                        result.getTotalElements(),
                        result.getTotalPages()
                )
        );
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAnyAuthority('TASK_READ_OWN','TASK_MANAGE')")
    public ApiResponse<TaskView> get(
            @PathVariable @Positive Long id,
            @AuthenticationPrincipal UserPrincipal actor
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                taskService.get(id, actor)
        );
    }
}
