package com.livestock.platform.security;

import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.common.web.RequestIds;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class SecurityAuditRecorder {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(SecurityAuditRecorder.class);

    private final AuditService auditService;

    public SecurityAuditRecorder(AuditService auditService) {
        this.auditService = auditService;
    }

    public void recordDenied(HttpServletRequest request, String result) {
        Long actorId = actorId(SecurityContextHolder.getContext().getAuthentication());
        try {
            auditService.appendInNewTransaction(new AuditEvent(
                    actorId,
                    "HTTP_ACCESS_DENIED",
                    "HTTP_REQUEST",
                    request.getRequestURI(),
                    RequestIds.current(),
                    result,
                    request.getRemoteAddr(),
                    request.getHeader("User-Agent"),
                    Map.of("method", request.getMethod())
            ));
        } catch (RuntimeException exception) {
            LOGGER.error(
                    "Could not persist denied-access audit type={}",
                    exception.getClass().getName()
            );
        }
    }

    private static Long actorId(Authentication authentication) {
        if (authentication == null
                || !(authentication.getPrincipal() instanceof UserPrincipal principal)) {
            return null;
        }
        try {
            return Long.valueOf(principal.userId());
        } catch (NumberFormatException exception) {
            return null;
        }
    }
}
