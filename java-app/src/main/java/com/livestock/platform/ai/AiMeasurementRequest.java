package com.livestock.platform.ai;

import com.fasterxml.jackson.annotation.JsonFormat;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

public record AiMeasurementRequest(
        String requestId,
        String operationId,
        String userId,
        AnimalSnapshot animalSnapshot,
        Integer ageMonth,
        Values current,
        List<HistoryItem> history,
        BigDecimal confidence,
        boolean useDemoHistory,
        int deadlineMs
) {
    public AiMeasurementRequest {
        history = List.copyOf(history);
    }

    public record AnimalSnapshot(
            String animalId,
            String species,
            String breed,
            String sex,
            @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
            LocalDate birthDate,
            Map<String, Object> attributes
    ) {
        public AnimalSnapshot {
            attributes = Map.copyOf(attributes);
        }
    }

    public record Values(
            BigDecimal bodyHeightCm,
            BigDecimal bodyLengthCm,
            BigDecimal chestGirthCm,
            BigDecimal chestDepthCm,
            BigDecimal chestWidthCm,
            BigDecimal weightKg
    ) {
    }

    public record HistoryItem(
            @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
            LocalDate measureDate,
            BigDecimal bodyHeightCm,
            BigDecimal bodyLengthCm,
            BigDecimal chestGirthCm,
            BigDecimal chestDepthCm,
            BigDecimal chestWidthCm,
            BigDecimal weightKg
    ) {
    }
}
