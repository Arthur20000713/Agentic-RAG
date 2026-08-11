package com.livestock.platform.ai;

import org.springframework.http.HttpStatus;

public class MeasurementClientException extends RuntimeException {

    private final HttpStatus status;
    private final String code;
    private final boolean retryable;

    public MeasurementClientException(
            HttpStatus status,
            String code,
            String message,
            boolean retryable,
            Throwable cause
    ) {
        super(message, cause);
        this.status = status;
        this.code = code;
        this.retryable = retryable;
    }

    public HttpStatus status() { return status; }
    public String code() { return code; }
    public boolean retryable() { return retryable; }
}
