package com.livestock.platform.security;

import java.util.Set;

public record UserPrincipal(
        String userId,
        String username,
        long securityVersion,
        Set<String> authorities
) {
    public UserPrincipal {
        authorities = authorities == null ? Set.of() : Set.copyOf(authorities);
    }
}
