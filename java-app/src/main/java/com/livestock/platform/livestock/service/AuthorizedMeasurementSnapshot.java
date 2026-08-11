package com.livestock.platform.livestock.service;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

public record AuthorizedMeasurementSnapshot(
        Long animalId,
        Long ownerId,
        String animalCode,
        String species,
        String breed,
        String sex,
        LocalDate birthDate,
        Long farmId,
        Integer ageMonth,
        List<HistoryItem> history
) {
    public AuthorizedMeasurementSnapshot {
        history = List.copyOf(history);
    }

    public record HistoryItem(
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
