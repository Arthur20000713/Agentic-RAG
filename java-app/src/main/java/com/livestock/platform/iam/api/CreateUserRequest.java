package com.livestock.platform.iam.api;

import com.livestock.platform.iam.domain.RoleCode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.Set;

public record CreateUserRequest(
        @NotBlank
        @Size(min = 3, max = 64)
        @Pattern(regexp = "^[A-Za-z0-9._-]+$")
        String username,
        @NotBlank @Size(min = 12, max = 72) String password,
        @NotEmpty @Size(max = 4) Set<RoleCode> roles
) {
}
