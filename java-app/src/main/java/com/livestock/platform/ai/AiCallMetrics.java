package com.livestock.platform.ai;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public final class AiCallMetrics {

    public enum Operation {
        CHAT("chat"),
        CHAT_RECONCILIATION("chat_reconciliation"),
        MEASUREMENT("measurement"),
        DOCUMENT_INDEX_SUBMIT("document_index_submit"),
        DOCUMENT_INDEX_RECONCILIATION("document_index_reconciliation");

        private final String tag;

        Operation(String tag) {
            this.tag = tag;
        }
    }

    private final MeterRegistry meterRegistry;

    public AiCallMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public <T> T record(
            Operation operation,
            Supplier<T> action,
            Function<T, String> successOutcome
    ) {
        Objects.requireNonNull(operation, "operation");
        Objects.requireNonNull(action, "action");
        Objects.requireNonNull(successOutcome, "successOutcome");
        long started = System.nanoTime();
        String outcome = "UNEXPECTED_ERROR";
        try {
            T result = action.get();
            outcome = normalize(successOutcome.apply(result));
            return result;
        } catch (RuntimeException exception) {
            outcome = failureOutcome(exception);
            throw exception;
        } finally {
            Tags tags = Tags.of("operation", operation.tag, "outcome", outcome);
            meterRegistry.counter("livestock.ai.calls", tags).increment();
            meterRegistry.timer("livestock.ai.duration", tags).record(
                    System.nanoTime() - started,
                    TimeUnit.NANOSECONDS
            );
        }
    }

    private static String failureOutcome(RuntimeException exception) {
        if (exception instanceof AiChatClientException failure) {
            return normalize(failure.code());
        }
        if (exception instanceof MeasurementClientException failure) {
            return normalize(failure.code());
        }
        if (exception instanceof KnowledgeClientException failure) {
            return normalize(failure.code());
        }
        return "UNEXPECTED_ERROR";
    }

    private static String normalize(String value) {
        if (value == null || value.isBlank()) {
            return "UNKNOWN";
        }
        String normalized = value.trim().toUpperCase(Locale.ROOT);
        return normalized.matches("[A-Z0-9_]{1,64}") ? normalized : "UNKNOWN";
    }
}
