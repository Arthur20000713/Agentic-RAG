package com.livestock.platform.audit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.doThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
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
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
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
class P3AuditAtomicityIntegrationTest {

    private static final String ADMIN_USERNAME = "p3-atomicity-admin";
    private static final String ADMIN_PASSWORD = "P3-atomicity-admin-password";

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("livestock_app")
            .withUsername("livestock_app")
            .withPassword("p3-atomicity-mysql-password");

    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4-alpine")
            .withExposedPorts(6379);

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @MockitoSpyBean
    AuditService auditService;

    @DynamicPropertySource
    static void p3AtomicityProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", REDIS::getFirstMappedPort);
        registry.add(
                "livestock.security.jwt-secret",
                () -> "p3-atomicity-jwt-secret-at-least-32-characters"
        );
        registry.add("livestock.bootstrap-admin.enabled", () -> "true");
        registry.add("livestock.bootstrap-admin.username", () -> ADMIN_USERNAME);
        registry.add("livestock.bootstrap-admin.password", () -> ADMIN_PASSWORD);
    }

    @Test
    void userInsertRollsBackWhenSuccessAuditCannotBeWritten() throws Exception {
        String accessToken = loginAdmin();
        String username = "p3-audit-rollback-user";
        String requestId = "req_p3_audit_rollback_0001";
        doThrow(new IllegalStateException("forced USER_CREATED audit failure"))
                .when(auditService)
                .append(argThat(event -> "USER_CREATED".equals(event.action())));

        mockMvc.perform(
                        post("/api/v1/users")
                                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsBytes(Map.of(
                                        "username", username,
                                        "password", "P3-audit-rollback-password",
                                        "roles", new String[]{"USER"}
                                )))
                )
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.requestId").value(requestId))
                .andExpect(jsonPath("$.error.code").value("INTERNAL_ERROR"));

        Integer userCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM sys_user WHERE username = ?",
                Integer.class,
                username
        );
        Integer successAuditCount = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM audit_log
                WHERE request_id = ?
                  AND action = 'USER_CREATED'
                  AND result = 'SUCCESS'
                """,
                Integer.class,
                requestId
        );
        assertThat(userCount).isZero();
        assertThat(successAuditCount).isZero();
    }

    private String loginAdmin() throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/auth/login")
                                .header(
                                        RequestIds.HEADER_NAME,
                                        "req_p3_atomicity_login_0001"
                                )
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsBytes(Map.of(
                                        "username", ADMIN_USERNAME,
                                        "password", ADMIN_PASSWORD
                                )))
                )
                .andExpect(status().isOk())
                .andReturn();
        JsonNode response = objectMapper.readTree(
                result.getResponse().getContentAsByteArray()
        );
        return response.at("/data/accessToken").asText();
    }
}
