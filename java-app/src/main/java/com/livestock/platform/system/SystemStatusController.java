package com.livestock.platform.system;

import com.livestock.platform.common.api.ApiResponse;
import com.livestock.platform.common.web.RequestIds;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/system")
public class SystemStatusController {

    private final SystemStatusService systemStatusService;

    public SystemStatusController(SystemStatusService systemStatusService) {
        this.systemStatusService = systemStatusService;
    }

    @GetMapping("/status")
    public ApiResponse<SystemStatusResponse> status() {
        return ApiResponse.success(RequestIds.current(), systemStatusService.status());
    }
}
