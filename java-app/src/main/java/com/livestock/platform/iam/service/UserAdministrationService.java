package com.livestock.platform.iam.service;

import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.iam.api.ChangeUserStatusRequest;
import com.livestock.platform.iam.api.CreateUserRequest;
import com.livestock.platform.iam.api.ReplaceUserRolesRequest;
import com.livestock.platform.iam.api.UserListResponse;
import com.livestock.platform.iam.api.UserView;
import com.livestock.platform.iam.domain.Role;
import com.livestock.platform.iam.domain.RoleCode;
import com.livestock.platform.iam.domain.UserAccount;
import com.livestock.platform.iam.domain.UserStatus;
import com.livestock.platform.iam.repository.RoleRepository;
import com.livestock.platform.iam.repository.UserAccountRepository;
import com.livestock.platform.security.UserPrincipal;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserAdministrationService {

    private final UserAccountRepository userAccountRepository;
    private final RoleRepository roleRepository;
    private final PasswordEncoder passwordEncoder;
    private final AuditService auditService;

    public UserAdministrationService(
            UserAccountRepository userAccountRepository,
            RoleRepository roleRepository,
            PasswordEncoder passwordEncoder,
            AuditService auditService
    ) {
        this.userAccountRepository = userAccountRepository;
        this.roleRepository = roleRepository;
        this.passwordEncoder = passwordEncoder;
        this.auditService = auditService;
    }

    @Transactional(readOnly = true)
    public UserListResponse list(int page, int size) {
        Page<UserAccount> users = userAccountRepository.findAll(
                PageRequest.of(
                        page,
                        size,
                        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
                )
        );
        return new UserListResponse(
                users.getContent().stream().map(UserView::from).toList(),
                users.getNumber(),
                users.getSize(),
                users.getTotalElements(),
                users.getTotalPages()
        );
    }

    @Transactional(readOnly = true)
    public UserView getVisibleUser(Long id, UserPrincipal actor) {
        boolean canManageUsers = actor.authorities().contains("USER_MANAGE");
        if (!String.valueOf(id).equals(actor.userId()) && !canManageUsers) {
            throw new AccessDeniedException("Access is denied");
        }
        return UserView.from(findUser(id));
    }

    @Transactional
    public UserView create(
            CreateUserRequest request,
            UserPrincipal actor,
            AuditRequestMetadata requestMetadata
    ) {
        String username = normalizeUsername(request.username());
        if (userAccountRepository.existsByUsernameIgnoreCase(username)) {
            throw conflict("USERNAME_ALREADY_EXISTS", "The username is already in use");
        }
        List<Role> roles = requiredRoles(request.roles());
        UserAccount user = new UserAccount(username, passwordEncoder.encode(request.password()));
        user.replaceRoles(roles);
        try {
            userAccountRepository.saveAndFlush(user);
        } catch (DataIntegrityViolationException exception) {
            throw conflict("USERNAME_ALREADY_EXISTS", "The username is already in use");
        }
        appendAudit(
                actor,
                "USER_CREATED",
                user,
                requestMetadata,
                Map.of("username", username, "roles", request.roles())
        );
        return UserView.from(user);
    }

    @Transactional
    public UserView changeStatus(
            Long id,
            ChangeUserStatusRequest request,
            UserPrincipal actor,
            AuditRequestMetadata requestMetadata
    ) {
        UserAccount user = findUser(id);
        requireVersion(user, request.version());
        if (request.status() == UserStatus.DISABLED
                && hasRole(user, RoleCode.ADMIN)
                && userAccountRepository.countByStatusAndRoleCode(
                        UserStatus.ENABLED,
                        RoleCode.ADMIN
                ) <= 1) {
            throw conflict(
                    "LAST_ACTIVE_ADMIN",
                    "The last enabled administrator cannot be disabled"
            );
        }
        UserStatus previousStatus = user.getStatus();
        user.changeStatus(request.status());
        userAccountRepository.saveAndFlush(user);
        appendAudit(
                actor,
                "USER_STATUS_CHANGED",
                user,
                requestMetadata,
                Map.of("from", previousStatus, "to", request.status())
        );
        return UserView.from(user);
    }

    @Transactional
    public UserView replaceRoles(
            Long id,
            ReplaceUserRolesRequest request,
            UserPrincipal actor,
            AuditRequestMetadata requestMetadata
    ) {
        UserAccount user = findUser(id);
        requireVersion(user, request.version());
        Set<RoleCode> previousRoles = user.getRoles().stream()
                .map(Role::getCode)
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
        if (previousRoles.contains(RoleCode.ADMIN)
                && !request.roles().contains(RoleCode.ADMIN)
                && user.getStatus() == UserStatus.ENABLED
                && userAccountRepository.countByStatusAndRoleCode(
                        UserStatus.ENABLED,
                        RoleCode.ADMIN
                ) <= 1) {
            throw conflict(
                    "LAST_ACTIVE_ADMIN",
                    "The last enabled administrator must retain the ADMIN role"
            );
        }
        List<Role> roles = requiredRoles(request.roles());
        user.replaceRoles(roles);
        userAccountRepository.saveAndFlush(user);
        appendAudit(
                actor,
                "USER_ROLES_CHANGED",
                user,
                requestMetadata,
                Map.of("from", previousRoles, "to", request.roles())
        );
        return UserView.from(user);
    }

    private UserAccount findUser(Long id) {
        return userAccountRepository.findOneById(id)
                .orElseThrow(() -> new ApiException(
                        HttpStatus.NOT_FOUND,
                        "USER_NOT_FOUND",
                        "The user was not found"
                ));
    }

    private List<Role> requiredRoles(Set<RoleCode> roleCodes) {
        List<Role> roles = roleRepository.findAllByCodeIn(roleCodes);
        if (roles.size() != roleCodes.size()) {
            throw new ApiException(
                    HttpStatus.UNPROCESSABLE_ENTITY,
                    "ROLE_NOT_FOUND",
                    "One or more roles were not found"
            );
        }
        return roles;
    }

    private void appendAudit(
            UserPrincipal actor,
            String action,
            UserAccount user,
            AuditRequestMetadata metadata,
            Map<String, ?> details
    ) {
        auditService.append(new AuditEvent(
                Long.valueOf(actor.userId()),
                action,
                "USER",
                String.valueOf(user.getId()),
                RequestIds.current(),
                "SUCCESS",
                metadata.clientIp(),
                metadata.userAgent(),
                details
        ));
    }

    private static void requireVersion(UserAccount user, long expectedVersion) {
        if (user.getVersion() != expectedVersion) {
            throw conflict(
                    "VERSION_CONFLICT",
                    "The user changed before this request completed"
            );
        }
    }

    private static boolean hasRole(UserAccount user, RoleCode code) {
        return user.getRoles().stream().anyMatch(role -> role.getCode() == code);
    }

    private static String normalizeUsername(String username) {
        return username.trim().toLowerCase(Locale.ROOT);
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(HttpStatus.CONFLICT, code, message);
    }
}
