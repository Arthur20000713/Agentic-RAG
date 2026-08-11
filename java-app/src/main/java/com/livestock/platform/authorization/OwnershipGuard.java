package com.livestock.platform.authorization;

import java.util.Collection;
import java.util.Objects;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;

@Component
public class OwnershipGuard {

    public void requireOwnerOrAuthority(
            String actorId,
            String ownerId,
            Collection<String> authorities,
            String ownAuthority,
            String allAuthority
    ) {
        Objects.requireNonNull(authorities, "authorities");
        boolean hasAllAuthority = authorities.contains(allAuthority);
        boolean isOwner = actorId != null && actorId.equals(ownerId);
        boolean hasOwnAuthority = authorities.contains(ownAuthority);

        if (hasAllAuthority || (isOwner && hasOwnAuthority)) {
            return;
        }
        throw new AccessDeniedException("Resource access denied");
    }
}
