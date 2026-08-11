package com.livestock.platform.auth.service;

import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.auth.api.TokenPairResponse;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.iam.api.UserView;
import com.livestock.platform.iam.domain.UserAccount;
import com.livestock.platform.iam.domain.UserStatus;
import com.livestock.platform.iam.repository.UserAccountRepository;
import com.livestock.platform.iam.service.JpaUserSecurityReader;
import com.livestock.platform.security.JwtService;
import com.livestock.platform.security.RedisRefreshTokenFamilyStore;
import com.livestock.platform.security.SecurityStateUnavailableException;
import com.livestock.platform.security.UserPrincipal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthenticationService {

    private static final String DUMMY_PASSWORD =
            "not-a-real-password-used-only-to-equalize-login-work";

    private final UserAccountRepository userAccountRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final RedisRefreshTokenFamilyStore refreshTokenStore;
    private final AuditService auditService;
    private final String dummyPasswordHash;

    public AuthenticationService(
            UserAccountRepository userAccountRepository,
            PasswordEncoder passwordEncoder,
            JwtService jwtService,
            RedisRefreshTokenFamilyStore refreshTokenStore,
            AuditService auditService
    ) {
        this.userAccountRepository = userAccountRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.refreshTokenStore = refreshTokenStore;
        this.auditService = auditService;
        this.dummyPasswordHash = passwordEncoder.encode(DUMMY_PASSWORD);
    }

    @Transactional(readOnly = true)
    public TokenPairResponse login(
            String suppliedUsername,
            String suppliedPassword,
            AuditRequestMetadata metadata
    ) {
        String username = suppliedUsername.trim().toLowerCase(Locale.ROOT);
        UserAccount user = userAccountRepository.findByUsernameIgnoreCase(username)
                .orElse(null);
        String passwordHash = user == null ? dummyPasswordHash : user.getPasswordHash();
        boolean passwordMatches = passwordEncoder.matches(suppliedPassword, passwordHash);
        if (user == null || !passwordMatches || user.getStatus() != UserStatus.ENABLED) {
            appendLoginAudit(
                    null,
                    "FAILURE",
                    metadata,
                    Map.of("usernameHash", usernameHash(username))
            );
            throw authenticationFailed();
        }
        UserPrincipal principal = JpaUserSecurityReader.toPrincipal(user);
        RedisRefreshTokenFamilyStore.IssuedRefreshToken refreshToken =
                createRefreshFamily(principal);
        try {
            JwtService.AccessToken accessToken = jwtService.issueAccessToken(
                    principal,
                    refreshToken.familyId()
            );
            appendLoginAudit(
                    user.getId(),
                    "SUCCESS",
                    metadata,
                    Map.of("usernameHash", usernameHash(username))
            );
            return tokenPair(user, accessToken, refreshToken);
        } catch (RuntimeException exception) {
            revokeFamily(refreshToken.familyId());
            throw exception;
        }
    }

    @Transactional(readOnly = true)
    public TokenPairResponse refresh(
            String presentedRefreshToken,
            AuditRequestMetadata metadata
    ) {
        RedisRefreshTokenFamilyStore.RefreshRotationResult rotation;
        try {
            rotation = refreshTokenStore.rotate(presentedRefreshToken);
        } catch (SecurityStateUnavailableException exception) {
            throw authStateUnavailable();
        }
        if (rotation.status()
                != RedisRefreshTokenFamilyStore.RefreshRotationStatus.ROTATED) {
            auditService.appendInNewTransaction(new AuditEvent(
                    null,
                    "REFRESH_TOKEN_REJECTED",
                    "AUTH_SESSION",
                    null,
                    RequestIds.current(),
                    "FAILURE",
                    metadata.clientIp(),
                    metadata.userAgent(),
                    Map.of("reason", rotation.status().name())
            ));
            throw invalidRefreshToken();
        }

        UserAccount user = parseUserId(rotation.userId());
        if (user == null
                || user.getStatus() != UserStatus.ENABLED
                || user.getSecurityVersion() != rotation.securityVersion()) {
            revokeFamily(rotation.familyId());
            throw invalidRefreshToken();
        }
        UserPrincipal principal = JpaUserSecurityReader.toPrincipal(user);
        try {
            JwtService.AccessToken accessToken = jwtService.issueAccessToken(
                    principal,
                    rotation.familyId()
            );
            auditService.appendInNewTransaction(new AuditEvent(
                    user.getId(),
                    "REFRESH_TOKEN_ROTATED",
                    "AUTH_SESSION",
                    rotation.familyId(),
                    RequestIds.current(),
                    "SUCCESS",
                    metadata.clientIp(),
                    metadata.userAgent(),
                    Map.of()
            ));
            return new TokenPairResponse(
                    "Bearer",
                    accessToken.token(),
                    accessToken.expiresAt(),
                    rotation.token(),
                    rotation.expiresAt(),
                    UserView.from(user)
            );
        } catch (RuntimeException exception) {
            revokeFamily(rotation.familyId());
            throw exception;
        }
    }

    public void logout(
            String rawAccessToken,
            UserPrincipal principal,
            AuditRequestMetadata metadata
    ) {
        JwtService.DecodedAccessToken accessToken = jwtService.decodeAccessToken(
                rawAccessToken
        );
        if (!principal.userId().equals(accessToken.userId())) {
            throw authenticationFailed();
        }
        revokeFamily(accessToken.sessionId());
        auditService.appendInNewTransaction(new AuditEvent(
                Long.valueOf(principal.userId()),
                "AUTH_SESSION_LOGOUT",
                "AUTH_SESSION",
                accessToken.sessionId(),
                RequestIds.current(),
                "SUCCESS",
                metadata.clientIp(),
                metadata.userAgent(),
                Map.of()
        ));
    }

    private void revokeFamily(String familyId) {
        try {
            refreshTokenStore.revokeFamily(familyId);
        } catch (SecurityStateUnavailableException exception) {
            throw authStateUnavailable();
        }
    }

    private RedisRefreshTokenFamilyStore.IssuedRefreshToken createRefreshFamily(
            UserPrincipal principal
    ) {
        try {
            return refreshTokenStore.createFamily(
                    principal.userId(),
                    principal.securityVersion()
            );
        } catch (SecurityStateUnavailableException exception) {
            throw authStateUnavailable();
        }
    }

    private UserAccount parseUserId(String userId) {
        try {
            return userAccountRepository.findOneById(Long.valueOf(userId)).orElse(null);
        } catch (NumberFormatException exception) {
            return null;
        }
    }

    private TokenPairResponse tokenPair(
            UserAccount user,
            JwtService.AccessToken accessToken,
            RedisRefreshTokenFamilyStore.IssuedRefreshToken refreshToken
    ) {
        return new TokenPairResponse(
                "Bearer",
                accessToken.token(),
                accessToken.expiresAt(),
                refreshToken.token(),
                refreshToken.expiresAt(),
                UserView.from(user)
        );
    }

    private void appendLoginAudit(
            Long actorId,
            String result,
            AuditRequestMetadata metadata,
            Map<String, ?> details
    ) {
        auditService.appendInNewTransaction(new AuditEvent(
                actorId,
                "USER_LOGIN",
                "AUTH_SESSION",
                null,
                RequestIds.current(),
                result,
                metadata.clientIp(),
                metadata.userAgent(),
                details
        ));
    }

    private static String usernameHash(String username) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(username.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash, 0, 12);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    private static ApiException authenticationFailed() {
        return new ApiException(
                HttpStatus.UNAUTHORIZED,
                "AUTHENTICATION_FAILED",
                "Authentication failed"
        );
    }

    private static ApiException invalidRefreshToken() {
        return new ApiException(
                HttpStatus.UNAUTHORIZED,
                "REFRESH_TOKEN_INVALID",
                "The refresh token is invalid"
        );
    }

    private static ApiException authStateUnavailable() {
        return new ApiException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "AUTH_STATE_UNAVAILABLE",
                "Authentication state is temporarily unavailable"
        );
    }
}
