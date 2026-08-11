package com.livestock.platform.security;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Autowired;

@Component
public final class ApiAccessDeniedHandler implements AccessDeniedHandler {

    private final SecurityErrorWriter errorWriter;
    private SecurityAuditRecorder auditRecorder;

    public ApiAccessDeniedHandler(SecurityErrorWriter errorWriter) {
        this.errorWriter = errorWriter;
    }

    @Autowired
    void setAuditRecorder(SecurityAuditRecorder auditRecorder) {
        this.auditRecorder = auditRecorder;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException accessDeniedException
    ) throws IOException, ServletException {
        if (auditRecorder != null) {
            auditRecorder.recordDenied(request, "FORBIDDEN");
        }
        errorWriter.write(
                response,
                HttpStatus.FORBIDDEN.value(),
                "ACCESS_DENIED",
                "Access is denied"
        );
    }
}
