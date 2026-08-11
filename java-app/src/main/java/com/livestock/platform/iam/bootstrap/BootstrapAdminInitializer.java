package com.livestock.platform.iam.bootstrap;

import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.iam.domain.Role;
import com.livestock.platform.iam.domain.RoleCode;
import com.livestock.platform.iam.domain.UserAccount;
import com.livestock.platform.iam.repository.RoleRepository;
import com.livestock.platform.iam.repository.UserAccountRepository;
import java.util.Locale;
import java.util.Map;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@EnableConfigurationProperties(BootstrapAdminProperties.class)
public class BootstrapAdminInitializer implements ApplicationRunner {

    private final BootstrapAdminProperties properties;
    private final UserAccountRepository userAccountRepository;
    private final RoleRepository roleRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuditService auditService;

    public BootstrapAdminInitializer(
            BootstrapAdminProperties properties,
            UserAccountRepository userAccountRepository,
            RoleRepository roleRepository,
            PasswordEncoder passwordEncoder,
            AuditService auditService
    ) {
        this.properties = properties;
        this.userAccountRepository = userAccountRepository;
        this.roleRepository = roleRepository;
        this.passwordEncoder = passwordEncoder;
        this.auditService = auditService;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments arguments) {
        if (!properties.enabled()) {
            return;
        }
        validateConfiguration();
        if (userAccountRepository.count() != 0) {
            return;
        }
        Role adminRole = roleRepository.findByCode(RoleCode.ADMIN)
                .orElseThrow(() -> new IllegalStateException("ADMIN role is missing"));
        String username = properties.username().trim().toLowerCase(Locale.ROOT);
        UserAccount admin = new UserAccount(
                username,
                passwordEncoder.encode(properties.password())
        );
        admin.replaceRoles(java.util.List.of(adminRole));
        userAccountRepository.saveAndFlush(admin);
        auditService.append(new AuditEvent(
                null,
                "BOOTSTRAP_ADMIN_CREATED",
                "USER",
                String.valueOf(admin.getId()),
                "req_bootstrap_admin",
                "SUCCESS",
                null,
                null,
                Map.of("username", username, "roles", java.util.List.of("ADMIN"))
        ));
    }

    private void validateConfiguration() {
        if (properties.username() == null || properties.username().isBlank()) {
            throw new IllegalStateException("Bootstrap admin username is required");
        }
        if (properties.password() == null || properties.password().length() < 12) {
            throw new IllegalStateException(
                    "Bootstrap admin password must contain at least 12 characters"
            );
        }
    }
}
