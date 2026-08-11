package com.livestock.platform.ai;

public final class AiChatClientException extends RuntimeException {

    private final String code;
    private final String remoteCode;
    private final boolean retryable;
    private final boolean submissionUnknown;
    private final boolean circuitFailure;

    public AiChatClientException(
            String code,
            String remoteCode,
            String message,
            boolean retryable,
            boolean submissionUnknown,
            boolean circuitFailure,
            Throwable cause
    ) {
        super(message, cause);
        this.code = code;
        this.remoteCode = remoteCode;
        this.retryable = retryable;
        this.submissionUnknown = submissionUnknown;
        this.circuitFailure = circuitFailure;
    }

    public String code() {
        return code;
    }

    public String remoteCode() {
        return remoteCode;
    }

    public boolean retryable() {
        return retryable;
    }

    public boolean submissionUnknown() {
        return submissionUnknown;
    }

    public boolean circuitFailure() {
        return circuitFailure;
    }
}
