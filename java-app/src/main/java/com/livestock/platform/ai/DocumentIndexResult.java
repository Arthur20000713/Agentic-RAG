package com.livestock.platform.ai;

public record DocumentIndexResult(
        String documentId,
        String ragDocumentId,
        String collection,
        boolean indexed,
        boolean skipped,
        Integer chunkCount,
        ExecutionMode executionMode
) {
    public enum ExecutionMode {
        FAKE,
        REAL
    }
}
