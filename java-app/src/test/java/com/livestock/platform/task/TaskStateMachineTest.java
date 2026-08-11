package com.livestock.platform.task;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.task.domain.TaskStatus;
import com.livestock.platform.task.service.TaskStateMachine;
import java.util.Set;
import org.junit.jupiter.api.Test;

class TaskStateMachineTest {

    private final TaskStateMachine stateMachine = new TaskStateMachine();

    @Test
    void acceptsEverySpecifiedForwardTransition() {
        Set<Transition> allowed = Set.of(
                new Transition(TaskStatus.CREATED, TaskStatus.RUNNING),
                new Transition(TaskStatus.CREATED, TaskStatus.FAILED),
                new Transition(TaskStatus.CREATED, TaskStatus.TIMED_OUT),
                new Transition(TaskStatus.CREATED, TaskStatus.CANCELLED),
                new Transition(TaskStatus.CREATED, TaskStatus.SUBMIT_UNKNOWN),
                new Transition(TaskStatus.RUNNING, TaskStatus.SUCCEEDED),
                new Transition(TaskStatus.RUNNING, TaskStatus.FAILED),
                new Transition(TaskStatus.RUNNING, TaskStatus.TIMED_OUT),
                new Transition(TaskStatus.RUNNING, TaskStatus.CANCELLED),
                new Transition(TaskStatus.RUNNING, TaskStatus.SUBMIT_UNKNOWN),
                new Transition(TaskStatus.SUBMIT_UNKNOWN, TaskStatus.RUNNING),
                new Transition(TaskStatus.SUBMIT_UNKNOWN, TaskStatus.SUCCEEDED),
                new Transition(TaskStatus.SUBMIT_UNKNOWN, TaskStatus.FAILED),
                new Transition(TaskStatus.SUBMIT_UNKNOWN, TaskStatus.TIMED_OUT),
                new Transition(TaskStatus.SUBMIT_UNKNOWN, TaskStatus.CANCELLED)
        );

        allowed.forEach(transition -> assertThatCode(
                () -> stateMachine.requireTransition(
                        transition.current(),
                        transition.next()
                )
        ).doesNotThrowAnyException());
    }

    @Test
    void sameStateIsAnIdempotentNoOp() {
        for (TaskStatus status : TaskStatus.values()) {
            assertThatCode(() -> stateMachine.requireTransition(status, status))
                    .doesNotThrowAnyException();
        }
    }

    @Test
    void terminalAndBackwardTransitionsAreRejected() {
        Set<Transition> rejected = Set.of(
                new Transition(TaskStatus.CREATED, TaskStatus.SUCCEEDED),
                new Transition(TaskStatus.RUNNING, TaskStatus.CREATED),
                new Transition(TaskStatus.SUCCEEDED, TaskStatus.RUNNING),
                new Transition(TaskStatus.FAILED, TaskStatus.RUNNING),
                new Transition(TaskStatus.TIMED_OUT, TaskStatus.RUNNING),
                new Transition(TaskStatus.CANCELLED, TaskStatus.RUNNING)
        );

        rejected.forEach(transition -> assertThatThrownBy(
                () -> stateMachine.requireTransition(
                        transition.current(),
                        transition.next()
                )
        )
                .isInstanceOf(ApiException.class)
                .extracting(exception -> ((ApiException) exception).code())
                .isEqualTo("ILLEGAL_TASK_TRANSITION"));
    }

    private record Transition(TaskStatus current, TaskStatus next) {
    }
}
