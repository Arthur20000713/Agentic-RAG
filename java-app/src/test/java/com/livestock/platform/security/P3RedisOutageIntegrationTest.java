package com.livestock.platform.security;

import static org.awaitility.Awaitility.await;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
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
class P3RedisOutageIntegrationTest {

    private static final String ADMIN_USERNAME = "p3-outage-admin";
    private static final String ADMIN_PASSWORD = "P3-outage-admin-password-2026";

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("livestock_app")
            .withUsername("livestock_app")
            .withPassword("p3-outage-mysql-password");

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>("redis:7.4-alpine")
                    .withExposedPorts(6379);

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @DynamicPropertySource
    static void outageProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", REDIS::getFirstMappedPort);
        registry.add("spring.data.redis.timeout", () -> "1s");
        registry.add(
                "livestock.security.jwt-secret",
                () -> "p3-outage-integration-jwt-secret-at-least-32-characters"
        );
        registry.add("livestock.bootstrap-admin.enabled", () -> "true");
        registry.add("livestock.bootstrap-admin.username", () -> ADMIN_USERNAME);
        registry.add("livestock.bootstrap-admin.password", () -> ADMIN_PASSWORD);
    }

    @Test
    void redisOutageFailsClosedAndRecovers() throws Exception {
        Tokens refreshSession = login("req_p3_outage_seed_refresh_0001");
        Tokens protectedSession = login("req_p3_outage_seed_protected_0001");
        Tokens logoutSession = login("req_p3_outage_seed_logout_0001");
        boolean redisPaused = false;
        try {
            REDIS.getDockerClient()
                    .pauseContainerCmd(REDIS.getContainerId())
                    .exec();
            redisPaused = true;

            expectAuthStateUnavailable(
                    post("/api/v1/auth/login")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(json(Map.of(
                                    "username", ADMIN_USERNAME,
                                    "password", ADMIN_PASSWORD
                            ))),
                    "req_p3_outage_login_0001"
            );
            expectAuthStateUnavailable(
                    post("/api/v1/auth/refresh")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(json(Map.of(
                                    "refreshToken",
                                    refreshSession.refreshToken()
                            ))),
                    "req_p3_outage_refresh_0001"
            );
            expectAuthStateUnavailable(
                    get("/api/v1/users")
                            .header(
                                    HttpHeaders.AUTHORIZATION,
                                    bearer(protectedSession.accessToken())
                            ),
                    "req_p3_outage_protected_0001"
            );
            expectAuthStateUnavailable(
                    post("/api/v1/auth/logout")
                            .header(
                                    HttpHeaders.AUTHORIZATION,
                                    bearer(logoutSession.accessToken())
                            ),
                    "req_p3_outage_logout_0001"
            );

            mockMvc.perform(
                            get("/actuator/health/liveness")
                                    .header(
                                            RequestIds.HEADER_NAME,
                                            "req_p3_outage_liveness_0001"
                                    )
                    )
                    .andExpect(status().isOk())
                    .andExpect(header().string(
                            RequestIds.HEADER_NAME,
                            "req_p3_outage_liveness_0001"
                    ))
                    .andExpect(jsonPath("$.status").value("UP"));
            mockMvc.perform(
                            get("/actuator/health/readiness")
                                    .header(
                                            RequestIds.HEADER_NAME,
                                            "req_p3_outage_readiness_0001"
                                    )
                    )
                    .andExpect(status().isServiceUnavailable())
                    .andExpect(header().string(
                            RequestIds.HEADER_NAME,
                            "req_p3_outage_readiness_0001"
                    ))
                    .andExpect(jsonPath("$.status").value("DOWN"));
        } finally {
            if (redisPaused) {
                REDIS.getDockerClient()
                        .unpauseContainerCmd(REDIS.getContainerId())
                        .exec();
            }
        }

        AtomicReference<Tokens> recoveredTokens = new AtomicReference<>();
        await()
                .atMost(Duration.ofSeconds(30))
                .pollInterval(Duration.ofMillis(500))
                .ignoreExceptions()
                .untilAsserted(() -> recoveredTokens.set(
                        login("req_p3_outage_recovery_0001")
                ));
        org.assertj.core.api.Assertions.assertThat(recoveredTokens.get().accessToken())
                .isNotBlank();
    }

    private void expectAuthStateUnavailable(
            org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request,
            String requestId
    ) throws Exception {
        mockMvc.perform(request.header(RequestIds.HEADER_NAME, requestId))
                .andExpect(status().isServiceUnavailable())
                .andExpect(header().string(RequestIds.HEADER_NAME, requestId))
                .andExpect(jsonPath("$.requestId").value(requestId))
                .andExpect(jsonPath("$.error.code").value("AUTH_STATE_UNAVAILABLE"))
                .andExpect(jsonPath("$.error.message").value(
                        "Authentication state is temporarily unavailable"
                ));
    }

    private Tokens login(String requestId) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/auth/login")
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", ADMIN_USERNAME,
                                        "password", ADMIN_PASSWORD
                                )))
                )
                .andExpect(status().isOk())
                .andExpect(header().string(RequestIds.HEADER_NAME, requestId))
                .andExpect(jsonPath("$.requestId").value(requestId))
                .andReturn();
        JsonNode data = objectMapper.readTree(result.getResponse().getContentAsByteArray())
                .path("data");
        return new Tokens(
                data.path("accessToken").asText(),
                data.path("refreshToken").asText()
        );
    }

    private String json(Object value) throws Exception {
        return objectMapper.writeValueAsString(value);
    }

    private static String bearer(String accessToken) {
        return "Bearer " + accessToken;
    }

    private record Tokens(String accessToken, String refreshToken) {
    }
}
