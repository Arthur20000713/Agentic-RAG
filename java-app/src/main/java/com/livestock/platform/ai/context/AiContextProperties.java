package com.livestock.platform.ai.context;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "livestock.ai-context")
@Validated
public class AiContextProperties {

    @NotBlank
    private String keyPrefix = "java:ai-context:";

    @NotNull
    private Duration ttl = Duration.ofHours(24);

    @Positive
    private int maxBytes = 65_536;

    public String keyPrefix() {
        return keyPrefix;
    }

    public void setKeyPrefix(String keyPrefix) {
        this.keyPrefix = keyPrefix;
    }

    public Duration ttl() {
        return ttl;
    }

    public void setTtl(Duration ttl) {
        this.ttl = ttl;
    }

    public int maxBytes() {
        return maxBytes;
    }

    public void setMaxBytes(int maxBytes) {
        this.maxBytes = maxBytes;
    }

    @AssertTrue(message = "ttl must be positive")
    public boolean isTtlPositive() {
        return ttl == null || (!ttl.isZero() && !ttl.isNegative());
    }
}
