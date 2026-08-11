package com.livestock.platform.security;

public class SecurityStateUnavailableException extends RuntimeException {

    public SecurityStateUnavailableException(String message) {
        super(message);
    }

    public SecurityStateUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
