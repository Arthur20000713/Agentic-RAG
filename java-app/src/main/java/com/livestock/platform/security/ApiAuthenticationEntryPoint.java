package com.livestock.platform.security;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Autowired;

@Component
public final class ApiAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private final SecurityErrorWriter errorWriter;
    private SecurityAuditRecorder auditRecorder;

    public ApiAuthenticationEntryPoint(SecurityErrorWriter errorWriter) {
        this.errorWriter = errorWriter;
    }

    @Autowired
    void setAuditRecorder(SecurityAuditRecorder auditRecorder) {
        this.auditRecorder = auditRecorder;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException
    ) throws IOException, ServletException {
        if (auditRecorder != null) {
            auditRecorder.recordDenied(request, "UNAUTHENTICATED");
        }
        errorWriter.write(
                response,
                HttpStatus.UNAUTHORIZED.value(),
                "AUTHENTICATION_REQUIRED",
                "Authentication is required"
        );
    }
}
