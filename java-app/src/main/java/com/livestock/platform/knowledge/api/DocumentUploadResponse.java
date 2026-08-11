package com.livestock.platform.knowledge.api;

import com.livestock.platform.task.api.TaskView;

public record DocumentUploadResponse(
        KnowledgeDocumentView document,
        TaskView task,
        boolean idempotentReplay
) {
}
