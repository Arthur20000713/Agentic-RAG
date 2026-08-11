package com.livestock.platform.system;

import java.util.Map;

public record SystemStatusResponse(
        String service,
        Map<String, DependencyStatus> dependencies
) {
}
