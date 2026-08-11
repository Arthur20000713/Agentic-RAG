package com.livestock.platform.audit.api;

import com.livestock.platform.audit.AuditQueryService;
import com.livestock.platform.common.api.ApiResponse;
import com.livestock.platform.common.web.RequestIds;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/audit-logs")
public class AuditLogController {

    private final AuditQueryService auditQueryService;

    public AuditLogController(AuditQueryService auditQueryService) {
        this.auditQueryService = auditQueryService;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('AUDIT_READ')")
    public ApiResponse<AuditLogListResponse> list(
            @RequestParam(required = false) String requestId,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "50") @Min(1) @Max(100) int size
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                auditQueryService.find(requestId, page, size)
        );
    }
}
