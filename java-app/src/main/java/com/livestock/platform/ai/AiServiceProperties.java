package com.livestock.platform.ai;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "livestock.ai-service")
@Validated
public class AiServiceProperties {

    @NotBlank
    private String baseUrl;

    @NotBlank
    @Size(min = 16)
    private String serviceToken;

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(2);

    @NotNull
    private Duration readTimeout = Duration.ofSeconds(3);

    @NotNull
    private Duration chatReadTimeout = Duration.ofSeconds(65);

    @NotNull
    private Duration measurementReadTimeout = Duration.ofSeconds(15);

    @NotNull
    private Duration recoveryLease = Duration.ofSeconds(90);

    @Positive
    private int chatMaxConcurrentCalls = 8;

    private boolean chatEnabled = true;

    public String baseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String serviceToken() {
        return serviceToken;
    }

    public void setServiceToken(String serviceToken) {
        this.serviceToken = serviceToken;
    }

    public Duration connectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration readTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }

    public Duration chatReadTimeout() {
        return chatReadTimeout;
    }

    public Duration measurementReadTimeout() {
        return measurementReadTimeout;
    }

    public void setMeasurementReadTimeout(Duration measurementReadTimeout) {
        this.measurementReadTimeout = measurementReadTimeout;
    }

    public void setChatReadTimeout(Duration chatReadTimeout) {
        this.chatReadTimeout = chatReadTimeout;
    }

    public Duration recoveryLease() {
        return recoveryLease;
    }

    public void setRecoveryLease(Duration recoveryLease) {
        if (recoveryLease != null
                && recoveryLease.compareTo(Duration.ofSeconds(60)) <= 0) {
            throw new IllegalArgumentException(
                    "AI recovery lease must exceed the 60 second chat deadline"
            );
        }
        this.recoveryLease = recoveryLease;
    }

    public int chatMaxConcurrentCalls() {
        return chatMaxConcurrentCalls;
    }

    public void setChatMaxConcurrentCalls(int chatMaxConcurrentCalls) {
        this.chatMaxConcurrentCalls = chatMaxConcurrentCalls;
    }

    public boolean chatEnabled() {
        return chatEnabled;
    }

    public void setChatEnabled(boolean chatEnabled) {
        this.chatEnabled = chatEnabled;
    }

    @Override
    public String toString() {
        return "AiServiceProperties{"
                + "baseUrl='" + baseUrl + '\''
                + ", serviceToken='[REDACTED]'"
                + ", connectTimeout=" + connectTimeout
                + ", readTimeout=" + readTimeout
                + ", chatReadTimeout=" + chatReadTimeout
                + ", measurementReadTimeout=" + measurementReadTimeout
                + ", recoveryLease=" + recoveryLease
                + ", chatMaxConcurrentCalls=" + chatMaxConcurrentCalls
                + ", chatEnabled=" + chatEnabled
                + '}';
    }
}
