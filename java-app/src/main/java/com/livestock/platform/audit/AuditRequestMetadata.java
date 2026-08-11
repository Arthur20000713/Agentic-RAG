package com.livestock.platform.audit;

import jakarta.servlet.http.HttpServletRequest;

public record AuditRequestMetadata(String clientIp, String userAgent) {

    public static AuditRequestMetadata from(HttpServletRequest request) {
        return new AuditRequestMetadata(
                request.getRemoteAddr(),
                request.getHeader("User-Agent")
        );
    }
}
