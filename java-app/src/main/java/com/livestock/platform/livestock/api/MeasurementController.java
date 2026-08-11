package com.livestock.platform.livestock.api;

import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.common.api.ApiResponse;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.livestock.service.MeasurementAnalysisService;
import com.livestock.platform.security.UserPrincipal;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/measurements")
public class MeasurementController {

    private final MeasurementAnalysisService analysisService;

    public MeasurementController(MeasurementAnalysisService analysisService) {
        this.analysisService = analysisService;
    }

    @PostMapping("/analyze")
    @PreAuthorize("hasAuthority('MEASUREMENT_ANALYZE')")
    public ApiResponse<MeasurementAnalyzeResponse> analyze(
            @RequestHeader("Idempotency-Key")
            @NotBlank
            @Size(min = 8, max = 128)
            @Pattern(regexp = "^[A-Za-z0-9._:-]+$") String idempotencyKey,
            @Valid @RequestBody MeasurementAnalyzeRequest payload,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest request
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                analysisService.analyze(
                        payload,
                        idempotencyKey,
                        actor,
                        AuditRequestMetadata.from(request)
                )
        );
    }
}
