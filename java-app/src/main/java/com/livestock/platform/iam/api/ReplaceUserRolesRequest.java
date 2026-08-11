package com.livestock.platform.iam.api;

import com.livestock.platform.iam.domain.RoleCode;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.util.Set;

public record ReplaceUserRolesRequest(
        @NotEmpty @Size(max = 4) Set<RoleCode> roles,
        @PositiveOrZero long version
) {
}
