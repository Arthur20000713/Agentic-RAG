package com.livestock.platform.livestock.api;

import java.util.List;

public record MeasurementAnalyzeResponse(
        String operationId,
        Outcome outcome,
        Long animalId,
        String animalCode,
        Analysis result
) {
    public enum Outcome {
        ANALYZED,
        INSUFFICIENT_DATA,
        LOW_CONFIDENCE
    }

    public record Analysis(
            String summary,
            List<String> abnormalItems,
            List<String> evidence,
            String recommendation,
            String report,
            boolean usedDemoHistory
    ) {
        public Analysis {
            abnormalItems = List.copyOf(abnormalItems);
            evidence = List.copyOf(evidence);
        }
    }
}
