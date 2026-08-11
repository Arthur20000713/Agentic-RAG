package com.livestock.platform.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class AiCallMetricsTest {

    @Test
    void recordsLowCardinalitySuccessAndDuration() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AiCallMetrics metrics = new AiCallMetrics(registry);

        String result = metrics.record(
                AiCallMetrics.Operation.CHAT,
                () -> "LOW_CONFIDENCE",
                value -> value
        );

        assertThat(result).isEqualTo("LOW_CONFIDENCE");
        assertThat(registry.counter(
                "livestock.ai.calls",
                "operation", "chat",
                "outcome", "LOW_CONFIDENCE"
        ).count()).isEqualTo(1.0);
        assertThat(registry.timer(
                "livestock.ai.duration",
                "operation", "chat",
                "outcome", "LOW_CONFIDENCE"
        ).count()).isEqualTo(1L);
    }

    @Test
    void recordsStableFailureCodeAndRethrows() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AiCallMetrics metrics = new AiCallMetrics(registry);
        AiChatClientException failure = new AiChatClientException(
                "AI_TIMEOUT",
                "MODEL_TIMEOUT",
                "timed out",
                true,
                false,
                true,
                null
        );

        assertThatThrownBy(() -> metrics.record(
                AiCallMetrics.Operation.CHAT,
                () -> {
                    throw failure;
                },
                value -> "ANSWERED"
        )).isSameAs(failure);

        assertThat(registry.counter(
                "livestock.ai.calls",
                "operation", "chat",
                "outcome", "AI_TIMEOUT"
        ).count()).isEqualTo(1.0);
        assertThat(registry.timer(
                "livestock.ai.duration",
                "operation", "chat",
                "outcome", "AI_TIMEOUT"
        ).count()).isEqualTo(1L);
    }
}
