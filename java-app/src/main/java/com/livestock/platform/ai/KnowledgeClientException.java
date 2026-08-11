package com.livestock.platform.ai;

public final class KnowledgeClientException extends RuntimeException {

    private final String code;
    private final boolean submissionUnknown;
    private final boolean retryable;

    public KnowledgeClientException(
            String code,
            String message,
            boolean submissionUnknown,
            boolean retryable,
            Throwable cause
    ) {
        super(message, cause);
        this.code = code;
        this.submissionUnknown = submissionUnknown;
        this.retryable = retryable;
    }

    public String code() {
        return code;
    }

    public boolean submissionUnknown() {
        return submissionUnknown;
    }

    public boolean retryable() {
        return retryable;
    }
}
