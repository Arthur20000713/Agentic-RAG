package com.livestock.platform.task.service;

import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.task.domain.TaskStatus;
import java.util.EnumMap;
import java.util.EnumSet;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

@Component
public final class TaskStateMachine {

    private static final Map<TaskStatus, Set<TaskStatus>> TRANSITIONS =
            transitions();

    public void requireTransition(TaskStatus current, TaskStatus next) {
        if (current == next) {
            return;
        }
        if (!TRANSITIONS.getOrDefault(current, Set.of()).contains(next)) {
            throw new ApiException(
                    HttpStatus.CONFLICT,
                    "ILLEGAL_TASK_TRANSITION",
                    "The requested task transition is not allowed"
            );
        }
    }

    private static Map<TaskStatus, Set<TaskStatus>> transitions() {
        Map<TaskStatus, Set<TaskStatus>> result = new EnumMap<>(TaskStatus.class);
        result.put(
                TaskStatus.CREATED,
                EnumSet.of(
                        TaskStatus.RUNNING,
                        TaskStatus.FAILED,
                        TaskStatus.TIMED_OUT,
                        TaskStatus.CANCELLED,
                        TaskStatus.SUBMIT_UNKNOWN
                )
        );
        result.put(
                TaskStatus.RUNNING,
                EnumSet.of(
                        TaskStatus.SUCCEEDED,
                        TaskStatus.FAILED,
                        TaskStatus.TIMED_OUT,
                        TaskStatus.CANCELLED,
                        TaskStatus.SUBMIT_UNKNOWN
                )
        );
        result.put(
                TaskStatus.SUBMIT_UNKNOWN,
                EnumSet.of(
                        TaskStatus.RUNNING,
                        TaskStatus.SUCCEEDED,
                        TaskStatus.FAILED,
                        TaskStatus.TIMED_OUT,
                        TaskStatus.CANCELLED
                )
        );
        return Map.copyOf(result);
    }
}
