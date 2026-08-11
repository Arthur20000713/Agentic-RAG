package com.livestock.platform.security;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties("livestock.security")
public record SecurityProperties(
        @NotBlank @Size(min = 32) String jwtSecret,
        @NotBlank String issuer,
        @NotBlank String audience,
        Duration accessTokenTtl,
        Duration refreshTokenTtl,
        Duration clockSkew,
        List<String> corsAllowedOrigins,
        String redisKeyPrefix
) {
    public SecurityProperties {
        accessTokenTtl = positiveOrDefault(accessTokenTtl, Duration.ofMinutes(15), "accessTokenTtl");
        refreshTokenTtl =
                positiveOrDefault(refreshTokenTtl, Duration.ofDays(7), "refreshTokenTtl");
        clockSkew = nonNegativeOrDefault(clockSkew, Duration.ofSeconds(30), "clockSkew");
        corsAllowedOrigins = corsAllowedOrigins == null ? List.of() : List.copyOf(corsAllowedOrigins);
        redisKeyPrefix = redisKeyPrefix == null || redisKeyPrefix.isBlank()
                ? "java:auth:"
                : redisKeyPrefix;
    }

    private static Duration positiveOrDefault(
            Duration candidate,
            Duration defaultValue,
            String name
    ) {
        Duration value = candidate == null ? defaultValue : candidate;
        if (value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(name + " must be positive");
        }
        return value;
    }

    private static Duration nonNegativeOrDefault(
            Duration candidate,
            Duration defaultValue,
            String name
    ) {
        Duration value = candidate == null ? defaultValue : candidate;
        if (value.isNegative()) {
            throw new IllegalArgumentException(name + " must not be negative");
        }
        return value;
    }
}
