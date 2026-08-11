package com.livestock.platform.conversation.api;

import com.livestock.platform.task.api.TaskView;

public record MessageSubmissionResponse(
        MessageView message,
        MessageView assistantMessage,
        TaskView task,
        boolean replayed
) {
}
