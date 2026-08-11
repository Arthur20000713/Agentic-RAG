package com.livestock.platform.iam.api;

import com.livestock.platform.iam.domain.RoleCode;
import com.livestock.platform.iam.domain.UserAccount;
import com.livestock.platform.iam.domain.UserStatus;
import java.time.Instant;
import java.util.Set;
import java.util.TreeSet;

public record UserView(
        String id,
        String username,
        UserStatus status,
        Set<RoleCode> roles,
        long version,
        Instant createdAt,
        Instant updatedAt
) {
    public static UserView from(UserAccount user) {
        TreeSet<RoleCode> roleCodes = new TreeSet<>();
        user.getRoles().forEach(role -> roleCodes.add(role.getCode()));
        return new UserView(
                String.valueOf(user.getId()),
                user.getUsername(),
                user.getStatus(),
                Set.copyOf(roleCodes),
                user.getVersion(),
                user.getCreatedAt(),
                user.getUpdatedAt()
        );
    }
}
