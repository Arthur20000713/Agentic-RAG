package com.livestock.platform.task.domain;

public enum TaskStatus {
    CREATED,
    RUNNING,
    SUCCEEDED,
    FAILED,
    TIMED_OUT,
    CANCELLED,
    SUBMIT_UNKNOWN
}
