package com.livestock.platform.livestock.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public record MeasurementAnalyzeRequest(
        @NotNull @Positive Long animalId,
        @NotNull @Valid BodyMeasurementValues current,
        @DecimalMin("0.0") @DecimalMax("1.0") BigDecimal confidence
) {
}
