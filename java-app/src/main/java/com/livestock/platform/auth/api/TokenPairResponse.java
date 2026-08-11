package com.livestock.platform.auth.api;

import com.livestock.platform.iam.api.UserView;
import java.time.Instant;

public record TokenPairResponse(
        String tokenType,
        String accessToken,
        Instant accessExpiresAt,
        String refreshToken,
        Instant refreshExpiresAt,
        UserView user
) {
}
