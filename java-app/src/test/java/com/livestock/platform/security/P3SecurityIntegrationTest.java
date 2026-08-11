package com.livestock.platform.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class P3SecurityIntegrationTest {

    private static final String ADMIN_USERNAME = "p3-admin";
    private static final String ADMIN_PASSWORD = "P3-admin-password-2026";

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("livestock_app")
            .withUsername("livestock_app")
            .withPassword("p3-integration-password");

    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4-alpine")
            .withExposedPorts(6379);

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @DynamicPropertySource
    static void p3Properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", REDIS::getFirstMappedPort);
        registry.add(
                "livestock.security.jwt-secret",
                () -> "p3-integration-jwt-secret-at-least-32-characters"
        );
        registry.add("livestock.bootstrap-admin.enabled", () -> "true");
        registry.add("livestock.bootstrap-admin.username", () -> ADMIN_USERNAME);
        registry.add("livestock.bootstrap-admin.password", () -> ADMIN_PASSWORD);
        registry.add(
                "livestock.security.cors-allowed-origins",
                () -> "https://allowed.p3.example"
        );
    }

    @Test
    void loginSucceedsAndWrongUnknownAndDisabledCredentialsShareOneResponse() throws Exception {
        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_admin_0001"
        );
        assertThat(admin.accessToken()).isNotBlank();
        assertThat(admin.refreshToken()).isNotBlank();

        JsonNode wrongPassword = failedLogin(
                ADMIN_USERNAME,
                "definitely-wrong-password",
                "req_p3_login_wrong_0001"
        );
        JsonNode unknownUser = failedLogin(
                "p3-user-does-not-exist",
                "definitely-wrong-password",
                "req_p3_login_unknown_0001"
        );

        CreatedUser disabled = createUser(
                admin.accessToken(),
                "p3-disabled-login",
                "P3-disabled-password",
                "USER",
                "req_p3_create_disabled_0001"
        );
        mockMvc.perform(
                        patch("/api/v1/users/{id}/status", disabled.id())
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_disable_login_0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "status", "DISABLED",
                                        "version", disabled.version()
                                )))
                )
                .andExpect(status().isOk());
        JsonNode disabledUser = failedLogin(
                "p3-disabled-login",
                "P3-disabled-password",
                "req_p3_login_disabled_0001"
        );

        assertThat(wrongPassword.path("error")).isEqualTo(unknownUser.path("error"));
        assertThat(disabledUser.path("error")).isEqualTo(unknownUser.path("error"));
        assertThat(unknownUser.at("/error/code").asText())
                .isEqualTo("AUTHENTICATION_FAILED");
    }

    @Test
    void javaOriginServesFrontendAssetsWithoutAuthentication() throws Exception {
        mockMvc.perform(get("/"))
                .andExpect(status().isOk())
                .andReturn();

        MvcResult index = mockMvc.perform(get("/index.html"))
                .andExpect(status().isOk())
                .andReturn();
        assertThat(index.getResponse().getContentType()).startsWith("text/html");
        assertThat(index.getResponse().getContentAsString())
                .contains("id=\"login-form\"")
                .contains("src=\"/app.js\"");

        MvcResult script = mockMvc.perform(get("/app.js"))
                .andExpect(status().isOk())
                .andReturn();
        assertThat(script.getResponse().getContentType())
                .contains("javascript");
        assertThat(script.getResponse().getContentAsString())
                .contains("/api/v1/auth/login")
                .contains("Idempotency-Key")
                .contains("contextVersion");
    }

    @Test
    void anonymousUsersIs401AndOrdinaryUserListIs403WithRequestIdEnvelope() throws Exception {
        String anonymousRequestId = "req_p3_anonymous_users_0001";
        mockMvc.perform(
                        get("/api/v1/users")
                                .header(RequestIds.HEADER_NAME, anonymousRequestId)
                )
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        RequestIds.HEADER_NAME,
                        anonymousRequestId
                ))
                .andExpect(jsonPath("$.requestId").value(anonymousRequestId))
                .andExpect(jsonPath("$.error.code").value("AUTHENTICATION_REQUIRED"));
        assertDeniedAudit(
                anonymousRequestId,
                null,
                "UNAUTHENTICATED",
                "GET",
                "/api/v1/users"
        );

        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_forbidden_admin_0001"
        );
        createUser(
                admin.accessToken(),
                "p3-forbidden-user",
                "P3-forbidden-password",
                "USER",
                "req_p3_create_forbidden_0001"
        );
        Tokens user = login(
                "p3-forbidden-user",
                "P3-forbidden-password",
                "req_p3_login_forbidden_user_0001"
        );

        String forbiddenRequestId = "req_p3_forbidden_users_0001";
        mockMvc.perform(
                        get("/api/v1/users")
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header(HttpHeaders.USER_AGENT, bearer(user.accessToken()))
                                .header(RequestIds.HEADER_NAME, forbiddenRequestId)
                )
                .andExpect(status().isForbidden())
                .andExpect(header().string(
                        RequestIds.HEADER_NAME,
                        forbiddenRequestId
                ))
                .andExpect(jsonPath("$.requestId").value(forbiddenRequestId))
                .andExpect(jsonPath("$.error.code").value("ACCESS_DENIED"));
        assertDeniedAudit(
                forbiddenRequestId,
                Long.valueOf(user.userId()),
                "FORBIDDEN",
                "GET",
                "/api/v1/users"
        );
        String storedUserAgent = jdbcTemplate.queryForObject(
                "SELECT user_agent FROM audit_log WHERE request_id = ?",
                String.class,
                forbiddenRequestId
        );
        assertThat(storedUserAgent)
                .contains("[REDACTED]")
                .doesNotContain(user.accessToken());
    }

    @Test
    void lastEnabledAdministratorCannotBeDisabledOrLoseAdminRole() throws Exception {
        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_last_admin_0001"
        );
        MvcResult currentUser = mockMvc.perform(
                        get("/api/v1/users/{id}", admin.userId())
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_get_last_admin_0001")
                )
                .andExpect(status().isOk())
                .andReturn();
        long version = body(currentUser).at("/data/version").asLong();

        mockMvc.perform(
                        patch("/api/v1/users/{id}/status", admin.userId())
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_disable_last_admin_0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "status", "DISABLED",
                                        "version", version
                                )))
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("LAST_ACTIVE_ADMIN"));

        mockMvc.perform(
                        put("/api/v1/users/{id}/roles", admin.userId())
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_demote_last_admin_0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "roles", new String[]{"USER"},
                                        "version", version
                                )))
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("LAST_ACTIVE_ADMIN"));

        Map<String, Object> persisted = jdbcTemplate.queryForMap(
                """
                SELECT u.status,
                       COUNT(CASE WHEN r.code = 'ADMIN' THEN 1 END) AS admin_roles
                FROM sys_user u
                LEFT JOIN sys_user_role ur ON ur.user_id = u.id
                LEFT JOIN sys_role r ON r.id = ur.role_id
                WHERE u.id = ?
                GROUP BY u.id, u.status
                """,
                Long.valueOf(admin.userId())
        );
        assertThat(persisted.get("status")).isEqualTo("ENABLED");
        assertThat(((Number) persisted.get("admin_roles")).longValue()).isEqualTo(1L);
    }

    @Test
    void usernameUniquenessIsCaseInsensitive() throws Exception {
        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_duplicate_admin_0001"
        );
        createUser(
                admin.accessToken(),
                "p3-duplicate-user",
                "P3-duplicate-password",
                "USER",
                "req_p3_create_duplicate_first_0001"
        );

        mockMvc.perform(
                        post("/api/v1/users")
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(
                                        RequestIds.HEADER_NAME,
                                        "req_p3_create_duplicate_second_0001"
                                )
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", "P3-DUPLICATE-USER",
                                        "password", "P3-duplicate-password-other",
                                        "roles", new String[]{"USER"}
                                )))
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("USERNAME_ALREADY_EXISTS"));

        Integer duplicateCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM sys_user WHERE LOWER(username) = ?",
                Integer.class,
                "p3-duplicate-user"
        );
        assertThat(duplicateCount).isEqualTo(1);
    }

    @Test
    void staleUserVersionReturnsConflictWithoutOverwritingNewerState() throws Exception {
        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_stale_admin_0001"
        );
        CreatedUser user = createUser(
                admin.accessToken(),
                "p3-stale-version",
                "P3-stale-version-password",
                "USER",
                "req_p3_create_stale_0001"
        );

        mockMvc.perform(
                        put("/api/v1/users/{id}/roles", user.id())
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_first_version_write_0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "roles", new String[]{"VET"},
                                        "version", user.version()
                                )))
                )
                .andExpect(status().isOk());

        mockMvc.perform(
                        patch("/api/v1/users/{id}/status", user.id())
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_stale_version_0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "status", "DISABLED",
                                        "version", user.version()
                                )))
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("VERSION_CONFLICT"));

        assertThat(jdbcTemplate.queryForObject(
                "SELECT status FROM sys_user WHERE id = ?",
                String.class,
                Long.valueOf(user.id())
        )).isEqualTo("ENABLED");
    }

    @Test
    void corsPreflightAllowsOnlyConfiguredOriginWithoutCredentials() throws Exception {
        mockMvc.perform(
                        options("/api/v1/users")
                                .header(HttpHeaders.ORIGIN, "https://allowed.p3.example")
                                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                                .header(
                                        HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                                        "Authorization,X-Request-ID"
                                )
                )
                .andExpect(status().isOk())
                .andExpect(header().string(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://allowed.p3.example"
                ))
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS
                ));

        mockMvc.perform(
                        options("/api/v1/users")
                                .header(HttpHeaders.ORIGIN, "https://blocked.p3.example")
                                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                )
                .andExpect(status().isForbidden())
                .andExpect(header().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN
                ));
    }

    @Test
    void administratorCreatesUserWithoutLeakingPasswordHash() throws Exception {
        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_create_admin_0001"
        );
        String password = "P3-create-user-password";

        MvcResult result = mockMvc.perform(
                        post("/api/v1/users")
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_create_safe_0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", "p3-safe-created",
                                        "password", password,
                                        "roles", new String[]{"USER"}
                                )))
                )
                .andExpect(status().isCreated())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andExpect(jsonPath("$.data.username").value("p3-safe-created"))
                .andExpect(jsonPath("$.data.password").doesNotExist())
                .andExpect(jsonPath("$.data.passwordHash").doesNotExist())
                .andReturn();

        String response = result.getResponse().getContentAsString();
        String passwordHash = jdbcTemplate.queryForObject(
                "SELECT password_hash FROM sys_user WHERE username = ?",
                String.class,
                "p3-safe-created"
        );
        assertThat(response).doesNotContain(password, "$2a$", "$2b$", "$2y$");
        assertThat(passwordHash)
                .isNotEqualTo(password)
                .startsWith("$2");
    }

    @Test
    void ordinaryUserCanReadSelfButCannotReadAnotherUser() throws Exception {
        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_owner_admin_0001"
        );
        CreatedUser owner = createUser(
                admin.accessToken(),
                "p3-owner",
                "P3-owner-password",
                "USER",
                "req_p3_create_owner_0001"
        );
        CreatedUser other = createUser(
                admin.accessToken(),
                "p3-other",
                "P3-other-password",
                "USER",
                "req_p3_create_other_0001"
        );
        Tokens ownerTokens = login(
                "p3-owner",
                "P3-owner-password",
                "req_p3_login_owner_0001"
        );

        mockMvc.perform(
                        get("/api/v1/users/{id}", owner.id())
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(ownerTokens.accessToken())
                                )
                                .header(RequestIds.HEADER_NAME, "req_p3_get_self_0001")
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.id").value(owner.id()));

        mockMvc.perform(
                        get("/api/v1/users/{id}", other.id())
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(ownerTokens.accessToken())
                                )
                                .header(RequestIds.HEADER_NAME, "req_p3_get_other_0001")
                )
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.requestId").value("req_p3_get_other_0001"))
                .andExpect(jsonPath("$.error.code").value("ACCESS_DENIED"));
    }

    @Test
    void refreshRotationAndOldTokenReplayInvalidateTheSuccessor() throws Exception {
        Tokens original = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_refresh_0001"
        );
        Tokens successor = refresh(
                original.refreshToken(),
                "req_p3_refresh_rotate_0001"
        );
        assertThat(successor.refreshToken()).isNotEqualTo(original.refreshToken());

        failedRefresh(
                original.refreshToken(),
                "req_p3_refresh_replay_0001"
        );
        failedRefresh(
                successor.refreshToken(),
                "req_p3_refresh_successor_0001"
        );

        mockMvc.perform(
                        get("/api/v1/users/{id}", successor.userId())
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(successor.accessToken())
                                )
                                .header(RequestIds.HEADER_NAME, "req_p3_replay_access_0001")
                )
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void logoutInvalidatesOnlyTheCurrentAccessTokenFamily() throws Exception {
        Tokens sessionA = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_logout_a_0001"
        );
        Tokens sessionB = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_logout_b_0001"
        );

        mockMvc.perform(
                        post("/api/v1/auth/logout")
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(sessionA.accessToken())
                                )
                                .header(RequestIds.HEADER_NAME, "req_p3_logout_0001")
                )
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(jsonPath("$.data.revoked").value(true));

        mockMvc.perform(
                        get("/api/v1/users/{id}", sessionA.userId())
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(sessionA.accessToken())
                                )
                                .header(RequestIds.HEADER_NAME, "req_p3_logout_access_0001")
                )
                .andExpect(status().isUnauthorized());
        failedRefresh(sessionA.refreshToken(), "req_p3_logout_refresh_0001");

        mockMvc.perform(
                        get("/api/v1/users/{id}", sessionB.userId())
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(sessionB.accessToken())
                                )
                                .header(
                                        RequestIds.HEADER_NAME,
                                        "req_p3_other_session_access_0001"
                                )
                )
                .andExpect(status().isOk());
        refresh(sessionB.refreshToken(), "req_p3_other_session_refresh_0001");
    }

    @Test
    void roleAndStatusChangesInvalidatePreviouslyIssuedAccessTokens() throws Exception {
        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_change_admin_0001"
        );
        CreatedUser target = createUser(
                admin.accessToken(),
                "p3-change-target",
                "P3-change-password",
                "USER",
                "req_p3_create_change_0001"
        );
        Tokens beforeRoleChange = login(
                "p3-change-target",
                "P3-change-password",
                "req_p3_login_before_role_0001"
        );

        MvcResult roleResult = mockMvc.perform(
                        put("/api/v1/users/{id}/roles", target.id())
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_change_role_0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "roles", new String[]{"VET"},
                                        "version", target.version()
                                )))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.roles[0]").value("VET"))
                .andReturn();
        long versionAfterRoleChange = body(roleResult).at("/data/version").asLong();

        assertRejectedAccess(
                beforeRoleChange.accessToken(),
                target.id(),
                "req_p3_old_role_access_0001"
        );

        Tokens beforeDisable = login(
                "p3-change-target",
                "P3-change-password",
                "req_p3_login_before_disable_0001"
        );
        mockMvc.perform(
                        patch("/api/v1/users/{id}/status", target.id())
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .header(RequestIds.HEADER_NAME, "req_p3_change_status_0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "status", "DISABLED",
                                        "version", versionAfterRoleChange
                                )))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("DISABLED"));

        assertRejectedAccess(
                beforeDisable.accessToken(),
                target.id(),
                "req_p3_disabled_access_0001"
        );
        failedLogin(
                "p3-change-target",
                "P3-change-password",
                "req_p3_disabled_relogin_0001"
        );
    }

    @Test
    void auditQueryRequiresPermissionAndNeverReturnsCredentialSecrets() throws Exception {
        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p3_login_audit_admin_0001"
        );
        CreatedUser user = createUser(
                admin.accessToken(),
                "p3-audit-user",
                "P3-audit-user-password",
                "USER",
                "req_p3_create_audit_user_0001"
        );
        createUser(
                admin.accessToken(),
                "p3-auditor",
                "P3-auditor-password",
                "AUDITOR",
                "req_p3_create_auditor_0001"
        );
        Tokens userTokens = login(
                "p3-audit-user",
                "P3-audit-user-password",
                "req_p3_login_audit_user_0001"
        );

        mockMvc.perform(
                        get("/api/v1/audit-logs")
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(userTokens.accessToken())
                                )
                                .header(RequestIds.HEADER_NAME, "req_p3_audit_denied_0001")
                )
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("ACCESS_DENIED"));

        Tokens auditor = login(
                "p3-auditor",
                "P3-auditor-password",
                "req_p3_login_auditor_0001"
        );
        MvcResult result = mockMvc.perform(
                        get("/api/v1/audit-logs")
                                .param("requestId", "req_p3_create_audit_user_0001")
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(auditor.accessToken())
                                )
                                .header(RequestIds.HEADER_NAME, "req_p3_audit_allowed_0001")
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.totalElements").value(1))
                .andExpect(jsonPath("$.data.items[0].action").value("USER_CREATED"))
                .andExpect(jsonPath("$.data.items[0].resourceId").value(user.id()))
                .andReturn();

        String response = result.getResponse().getContentAsString();
        assertThat(response)
                .doesNotContain(
                        "P3-audit-user-password",
                        "P3-auditor-password",
                        admin.accessToken(),
                        admin.refreshToken(),
                        auditor.accessToken(),
                        auditor.refreshToken()
                );
    }

    @Test
    void prometheusRequiresAuditReadPermission() throws Exception {
        mockMvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isUnauthorized());

        Tokens admin = login(
                ADMIN_USERNAME,
                ADMIN_PASSWORD,
                "req_p7_metrics_admin_login_0001"
        );
        createUser(
                admin.accessToken(),
                "p7-metrics-user",
                "P7-metrics-user-password",
                "USER",
                "req_p7_metrics_create_user_0001"
        );
        Tokens user = login(
                "p7-metrics-user",
                "P7-metrics-user-password",
                "req_p7_metrics_user_login_0001"
        );

        mockMvc.perform(get("/actuator/prometheus")
                        .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken())))
                .andExpect(status().isForbidden());
        mockMvc.perform(get("/actuator/prometheus")
                        .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken())))
                .andExpect(status().isOk());
    }

    private CreatedUser createUser(
            String adminAccessToken,
            String username,
            String password,
            String role,
            String requestId
    ) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/users")
                                .header(HttpHeaders.AUTHORIZATION, bearer(adminAccessToken))
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", username,
                                        "password", password,
                                        "roles", new String[]{role}
                                )))
                )
                .andExpect(status().isCreated())
                .andReturn();
        JsonNode data = body(result).path("data");
        return new CreatedUser(data.path("id").asText(), data.path("version").asLong());
    }

    private Tokens login(String username, String password, String requestId) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/auth/login")
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", username,
                                        "password", password
                                )))
                )
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andExpect(jsonPath("$.requestId").value(requestId))
                .andExpect(jsonPath("$.data.tokenType").value("Bearer"))
                .andReturn();
        return tokens(body(result));
    }

    private JsonNode failedLogin(
            String username,
            String password,
            String requestId
    ) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/auth/login")
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", username,
                                        "password", password
                                )))
                )
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.requestId").value(requestId))
                .andExpect(jsonPath("$.error.code").value("AUTHENTICATION_FAILED"))
                .andReturn();
        return body(result);
    }

    private Tokens refresh(String refreshToken, String requestId) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/auth/refresh")
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of("refreshToken", refreshToken)))
                )
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CACHE_CONTROL, "no-store"))
                .andReturn();
        return tokens(body(result));
    }

    private void failedRefresh(String refreshToken, String requestId) throws Exception {
        mockMvc.perform(
                        post("/api/v1/auth/refresh")
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of("refreshToken", refreshToken)))
                )
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.requestId").value(requestId))
                .andExpect(jsonPath("$.error.code").value("REFRESH_TOKEN_INVALID"));
    }

    private void assertRejectedAccess(
            String accessToken,
            String userId,
            String requestId
    ) throws Exception {
        mockMvc.perform(
                        get("/api/v1/users/{id}", userId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(accessToken))
                                .header(RequestIds.HEADER_NAME, requestId)
                )
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.requestId").value(requestId))
                .andExpect(jsonPath("$.error.code").value("AUTHENTICATION_REQUIRED"));
    }

    private void assertDeniedAudit(
            String requestId,
            Long expectedActorId,
            String expectedResult,
            String expectedMethod,
            String expectedPath
    ) {
        Map<String, Object> audit = jdbcTemplate.queryForMap(
                """
                SELECT actor_id,
                       action,
                       result,
                       request_id,
                       resource_id,
                       JSON_UNQUOTE(JSON_EXTRACT(detail_json, '$.method')) AS http_method
                FROM audit_log
                WHERE request_id = ?
                """,
                requestId
        );
        if (expectedActorId == null) {
            assertThat(audit.get("actor_id")).isNull();
        } else {
            assertThat(((Number) audit.get("actor_id")).longValue())
                    .isEqualTo(expectedActorId);
        }
        assertThat(audit)
                .containsEntry("action", "HTTP_ACCESS_DENIED")
                .containsEntry("result", expectedResult)
                .containsEntry("request_id", requestId)
                .containsEntry("resource_id", expectedPath)
                .containsEntry("http_method", expectedMethod);
    }

    private Tokens tokens(JsonNode response) {
        JsonNode data = response.path("data");
        return new Tokens(
                data.path("accessToken").asText(),
                data.path("refreshToken").asText(),
                data.at("/user/id").asText()
        );
    }

    private JsonNode body(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsByteArray());
    }

    private String json(Object value) throws Exception {
        return objectMapper.writeValueAsString(value);
    }

    private static String bearer(String token) {
        return "Bearer " + token;
    }

    private record Tokens(String accessToken, String refreshToken, String userId) {
    }

    private record CreatedUser(String id, long version) {
    }
}
