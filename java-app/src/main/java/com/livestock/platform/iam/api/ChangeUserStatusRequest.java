package com.livestock.platform.iam.api;

import com.livestock.platform.iam.domain.UserStatus;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;

public record ChangeUserStatusRequest(
        @NotNull UserStatus status,
        @PositiveOrZero long version
) {
}
