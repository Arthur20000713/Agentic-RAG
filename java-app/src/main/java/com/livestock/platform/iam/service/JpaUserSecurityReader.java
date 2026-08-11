package com.livestock.platform.iam.service;

import com.livestock.platform.iam.domain.UserAccount;
import com.livestock.platform.iam.domain.UserStatus;
import com.livestock.platform.iam.repository.UserAccountRepository;
import com.livestock.platform.security.UserPrincipal;
import com.livestock.platform.security.UserSecurityReader;
import java.util.HashSet;
import java.util.Optional;
import java.util.Set;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class JpaUserSecurityReader implements UserSecurityReader {

    private final UserAccountRepository userAccountRepository;

    public JpaUserSecurityReader(UserAccountRepository userAccountRepository) {
        this.userAccountRepository = userAccountRepository;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<UserPrincipal> findActiveUser(String userId) {
        Long id;
        try {
            id = Long.valueOf(userId);
        } catch (NumberFormatException exception) {
            return Optional.empty();
        }
        return userAccountRepository.findOneById(id)
                .filter(user -> user.getStatus() == UserStatus.ENABLED)
                .map(JpaUserSecurityReader::toPrincipal);
    }

    public static UserPrincipal toPrincipal(UserAccount user) {
        Set<String> authorities = new HashSet<>();
        user.getRoles().forEach(role -> {
            authorities.add("ROLE_" + role.getCode().name());
            role.getPermissions().forEach(
                    permission -> authorities.add(permission.getCode().name())
            );
        });
        return new UserPrincipal(
                String.valueOf(user.getId()),
                user.getUsername(),
                user.getSecurityVersion(),
                authorities
        );
    }
}
