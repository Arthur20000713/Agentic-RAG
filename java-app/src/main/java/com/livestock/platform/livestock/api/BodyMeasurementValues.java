package com.livestock.platform.livestock.api;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMin;
import java.math.BigDecimal;

public record BodyMeasurementValues(
        @DecimalMin("0.0") BigDecimal bodyHeightCm,
        @DecimalMin("0.0") BigDecimal bodyLengthCm,
        @DecimalMin("0.0") BigDecimal chestGirthCm,
        @DecimalMin("0.0") BigDecimal chestDepthCm,
        @DecimalMin("0.0") BigDecimal chestWidthCm,
        @DecimalMin("0.0") BigDecimal weightKg
) {
    @JsonIgnore
    @AssertTrue(message = "at least one measurement value is required")
    public boolean isAnyValuePresent() {
        return bodyHeightCm != null || bodyLengthCm != null || chestGirthCm != null
                || chestDepthCm != null || chestWidthCm != null || weightKg != null;
    }
}
