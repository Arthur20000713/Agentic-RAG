package com.livestock.platform.ai;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("pythonAi")
public class PythonAiHealthIndicator implements HealthIndicator {

    private final PythonAiClient pythonAiClient;

    public PythonAiHealthIndicator(PythonAiClient pythonAiClient) {
        this.pythonAiClient = pythonAiClient;
    }

    @Override
    public Health health() {
        try {
            pythonAiClient.verifyConnection();
            return Health.up().withDetail("service", "livestock-ai-service").build();
        } catch (Exception exception) {
            return Health.down()
                    .withDetail("service", "livestock-ai-service")
                    .withDetail("reason", "AI service connection failed")
                    .build();
        }
    }
}
