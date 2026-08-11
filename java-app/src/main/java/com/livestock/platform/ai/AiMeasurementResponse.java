package com.livestock.platform.ai;

import java.util.List;

public record AiMeasurementResponse(
        String requestId,
        String operationId,
        String runId,
        Outcome outcome,
        Analysis result,
        String traceId
) {
    public enum Outcome {
        ANALYZED,
        INSUFFICIENT_DATA,
        LOW_CONFIDENCE
    }

    public record Analysis(
            String animalId,
            String summary,
            List<String> abnormalItems,
            List<String> evidence,
            String recommendation,
            String report,
            boolean usedDemoHistory
    ) {
    }
}
