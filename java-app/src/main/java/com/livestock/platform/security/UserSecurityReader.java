package com.livestock.platform.security;

import java.util.Optional;

@FunctionalInterface
public interface UserSecurityReader {

    Optional<UserPrincipal> findActiveUser(String userId);
}
