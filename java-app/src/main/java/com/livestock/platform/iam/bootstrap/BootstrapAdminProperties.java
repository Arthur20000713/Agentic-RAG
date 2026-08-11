package com.livestock.platform.iam.bootstrap;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("livestock.bootstrap-admin")
public record BootstrapAdminProperties(
        boolean enabled,
        String username,
        String password
) {
}
