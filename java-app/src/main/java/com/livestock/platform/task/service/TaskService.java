package com.livestock.platform.task.service;

import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.security.UserPrincipal;
import com.livestock.platform.task.api.TaskView;
import com.livestock.platform.task.domain.BizTask;
import com.livestock.platform.task.domain.TaskStatus;
import com.livestock.platform.task.repository.BizTaskRepository;
import java.time.Clock;
import java.util.Map;
import java.util.Objects;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {

    private final BizTaskRepository taskRepository;
    private final TaskStateMachine stateMachine;
    private final AuditService auditService;
    private final Clock clock;

    public TaskService(
            BizTaskRepository taskRepository,
            TaskStateMachine stateMachine,
            AuditService auditService,
            Clock clock
    ) {
        this.taskRepository = taskRepository;
        this.stateMachine = stateMachine;
        this.auditService = auditService;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public TaskView get(Long id, UserPrincipal actor) {
        BizTask task;
        if (actor.authorities().contains("TASK_MANAGE")) {
            task = taskRepository.findById(id).orElseThrow(TaskService::notFound);
        } else {
            task = taskRepository.findByIdAndOwnerId(id, Long.valueOf(actor.userId()))
                    .orElseThrow(TaskService::notFound);
        }
        return TaskView.from(task);
    }

    @Transactional(readOnly = true)
    public Page<TaskView> list(
            String scope,
            int page,
            int size,
            UserPrincipal actor
    ) {
        PageRequest request = PageRequest.of(
                page,
                size,
                Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
        );
        if ("all".equalsIgnoreCase(scope)) {
            if (!actor.authorities().contains("TASK_MANAGE")) {
                throw new AccessDeniedException("Access is denied");
            }
            return taskRepository.findAll(request).map(TaskView::from);
        }
        if (!"own".equalsIgnoreCase(scope)) {
            throw new ApiException(
                    HttpStatus.BAD_REQUEST,
                    "INVALID_SCOPE",
                    "Scope must be own or all"
            );
        }
        return taskRepository.findAllByOwnerId(
                Long.valueOf(actor.userId()),
                request
        ).map(TaskView::from);
    }

    @Transactional
    public TaskView transition(
            Long id,
            long expectedVersion,
            TaskStatus nextStatus,
            int progress,
            String resultRef,
            String errorCode,
            UserPrincipal actor,
            AuditRequestMetadata metadata
    ) {
        BizTask task = taskRepository.findById(id).orElseThrow(TaskService::notFound);
        if (task.getVersion() != expectedVersion) {
            throw conflict(
                    "VERSION_CONFLICT",
                    "The task changed before this update completed"
            );
        }
        stateMachine.requireTransition(task.getStatus(), nextStatus);
        if (task.getStatus() == nextStatus) {
            if (task.getProgress() == progress
                    && Objects.equals(task.getResultRef(), resultRef)
                    && Objects.equals(task.getErrorCode(), errorCode)) {
                return TaskView.from(task);
            }
            throw conflict(
                    "TASK_RESULT_CONFLICT",
                    "The repeated task transition has different result data"
            );
        }
        TaskStatus previous = task.getStatus();
        task.applyTransition(
                nextStatus,
                progress,
                resultRef,
                errorCode,
                clock.instant()
        );
        taskRepository.saveAndFlush(task);
        auditService.append(new AuditEvent(
                Long.valueOf(actor.userId()),
                "TASK_STATUS_CHANGED",
                "TASK",
                String.valueOf(task.getId()),
                RequestIds.current(),
                "SUCCESS",
                metadata.clientIp(),
                metadata.userAgent(),
                Map.of("from", previous, "to", nextStatus, "progress", progress)
        ));
        return TaskView.from(task);
    }

    private static ApiException notFound() {
        return new ApiException(
                HttpStatus.NOT_FOUND,
                "TASK_NOT_FOUND",
                "The task was not found"
        );
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message);
    }
}
