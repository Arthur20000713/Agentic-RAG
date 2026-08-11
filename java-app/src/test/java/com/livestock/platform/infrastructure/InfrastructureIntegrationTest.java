package com.livestock.platform.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.livestock.platform.common.web.RequestIds;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.context.support.WithMockUser;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class InfrastructureIntegrationTest {

    private static final String AI_SERVICE_TOKEN = "integration-ai-token-32-characters";

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("livestock_app")
            .withUsername("livestock_app")
            .withPassword("integration-password");

    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4-alpine")
            .withExposedPorts(6379);

    private static final AtomicBoolean PYTHON_AI_AVAILABLE = new AtomicBoolean(true);
    private static final ExecutorService PYTHON_AI_EXECUTOR =
            Executors.newSingleThreadExecutor(runnable -> {
                Thread thread = new Thread(runnable, "python-ai-test-stub");
                thread.setDaemon(true);
                return thread;
            });
    private static final HttpServer PYTHON_AI = startPythonAiStub();

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    StringRedisTemplate redisTemplate;

    @Autowired
    Flyway flyway;

    @Autowired
    MockMvc mockMvc;

    @DynamicPropertySource
    static void infrastructureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", REDIS::getFirstMappedPort);
        registry.add(
                "livestock.security.jwt-secret",
                () -> "integration-jwt-secret-32-characters-minimum"
        );
        registry.add(
                "livestock.ai-service.base-url",
                () -> "http://127.0.0.1:" + PYTHON_AI.getAddress().getPort()
        );
        registry.add("livestock.ai-service.service-token", () -> AI_SERVICE_TOKEN);
    }

    @AfterAll
    static void stopPythonAiStub() {
        PYTHON_AI.stop(0);
        PYTHON_AI_EXECUTOR.shutdownNow();
    }

    @Test
    @WithMockUser(username = "integration-user")
    void connectsToMysqlRedisAndProtectedPythonApi() throws Exception {
        assertThat(jdbcTemplate.queryForObject("SELECT 1", Integer.class)).isEqualTo(1);
        redisTemplate.opsForValue().set("p2:integration", "connected");
        assertThat(redisTemplate.opsForValue().get("p2:integration")).isEqualTo("connected");

        mockMvc.perform(
                        get("/api/v1/system/status")
                                .header(RequestIds.HEADER_NAME, "req_status_0001")
                )
                .andExpect(status().isOk())
                .andExpect(header().string(RequestIds.HEADER_NAME, "req_status_0001"))
                .andExpect(jsonPath("$.requestId").value("req_status_0001"))
                .andExpect(jsonPath("$.data.dependencies.mysql.status").value("UP"))
                .andExpect(jsonPath("$.data.dependencies.redis.status").value("UP"))
                .andExpect(jsonPath("$.data.dependencies.pythonAi.status").value("UP"));
    }

    @Test
    void flywayMigrationIsRepeatableAfterStartingFromEmptyDatabase() {
        assertThat(flyway.info().applied()).hasSize(7);
        assertThat(
                jdbcTemplate.queryForObject(
                        "SELECT schema_version FROM platform_schema_marker WHERE id = 1",
                        String.class
                )
        ).isEqualTo("P2_BASELINE");

        assertThat(flyway.migrate().migrationsExecuted).isZero();
        flyway.validate();
        assertThat(flyway.info().applied()).hasSize(7);
    }

    @Test
    void p4MigrationCreatesConversationMessageAndTaskConstraints() {
        assertThat(jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name IN ('conversation', 'conversation_message', 'biz_task')
                """,
                Integer.class
        )).isEqualTo(3);
        assertThat(jdbcTemplate.queryForObject(
                """
                SELECT character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'biz_task'
                  AND column_name = 'request_hash'
                """,
                Long.class
        )).isEqualTo(64L);
        assertThat(jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND (
                    (table_name = 'conversation_message'
                     AND index_name IN (
                       'uk_conversation_message_turn_role'
                     )
                     AND non_unique = 0)
                    OR
                    (table_name = 'biz_task'
                     AND index_name = 'uk_biz_task_owner_operation'
                     AND non_unique = 0)
                  )
                """,
                Integer.class
        )).isEqualTo(5);
        assertThat(jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = 'conversation_message'
                  AND index_name = 'idx_conversation_message_request_id'
                  AND column_name = 'request_id'
                  AND non_unique = 1
                """,
                Integer.class
        )).isOne();
    }

    @Test
    void v5UpgradePreservesExistingV4MessagesAndRelaxesRequestIdIndex() {
        try (MySQLContainer<?> upgradeMysql = new MySQLContainer<>("mysql:8.0.36")
                .withDatabaseName("livestock_upgrade")
                .withUsername("livestock_upgrade")
                .withPassword("upgrade-password")) {
            upgradeMysql.start();
            Flyway v4Flyway = Flyway.configure()
                    .dataSource(
                            upgradeMysql.getJdbcUrl(),
                            upgradeMysql.getUsername(),
                            upgradeMysql.getPassword()
                    )
                    .target(MigrationVersion.fromVersion("4"))
                    .load();
            assertThat(v4Flyway.migrate().migrationsExecuted).isEqualTo(4);
            JdbcTemplate upgradeJdbc = new JdbcTemplate(new DriverManagerDataSource(
                    upgradeMysql.getJdbcUrl(),
                    upgradeMysql.getUsername(),
                    upgradeMysql.getPassword()
            ));
            upgradeJdbc.update("""
                    INSERT INTO sys_user (
                        id, username, password_hash, status
                    ) VALUES (100, 'upgrade-user', 'not-used', 'ENABLED')
                    """);
            upgradeJdbc.update("""
                    INSERT INTO conversation (
                        id, owner_id, title, status
                    ) VALUES (100, 100, 'existing', 'ACTIVE')
                    """);
            upgradeJdbc.update("""
                    INSERT INTO conversation_message (
                        id, conversation_id, turn_id, role, content,
                        request_id, status, metadata_json
                    ) VALUES (
                        100, 100, 'turn-existing', 'USER', 'existing message',
                        'req-shared-upgrade', 'COMPLETED', JSON_OBJECT()
                    )
                    """);

            Flyway latestFlyway = Flyway.configure()
                    .dataSource(
                            upgradeMysql.getJdbcUrl(),
                            upgradeMysql.getUsername(),
                            upgradeMysql.getPassword()
                    )
                    .target(MigrationVersion.fromVersion("5"))
                    .load();
            assertThat(latestFlyway.migrate().migrationsExecuted).isOne();
            assertThat(latestFlyway.info().current().getVersion().getVersion())
                    .isEqualTo("5");
            assertThat(upgradeJdbc.queryForObject(
                    "SELECT content FROM conversation_message WHERE id = 100",
                    String.class
            )).isEqualTo("existing message");
            assertThat(upgradeJdbc.queryForObject(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.statistics
                    WHERE table_schema = DATABASE()
                      AND table_name = 'conversation_message'
                      AND index_name = 'idx_conversation_message_request_id'
                      AND non_unique = 1
                    """,
                    Integer.class
            )).isOne();
            upgradeJdbc.update("""
                    INSERT INTO conversation_message (
                        id, conversation_id, turn_id, role, content,
                        request_id, status, metadata_json
                    ) VALUES (
                        101, 100, 'turn-second', 'USER', 'second message',
                        'req-shared-upgrade', 'COMPLETED', JSON_OBJECT()
                    )
                    """);
            assertThat(upgradeJdbc.queryForObject(
                    """
                    SELECT COUNT(*) FROM conversation_message
                    WHERE request_id = 'req-shared-upgrade' AND role = 'USER'
                    """,
                    Integer.class
            )).isEqualTo(2);
        }
    }

    @Test
    void livenessAndReadinessAreSeparateAndHealthy() throws Exception {
        mockMvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));

        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void pythonFailureMakesReadinessDownWithoutChangingLiveness() throws Exception {
        PYTHON_AI_AVAILABLE.set(false);
        try {
            mockMvc.perform(get("/actuator/health/liveness"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.status").value("UP"));

            mockMvc.perform(get("/actuator/health/readiness"))
                    .andExpect(status().isServiceUnavailable())
                    .andExpect(jsonPath("$.status").value("DOWN"));
        } finally {
            PYTHON_AI_AVAILABLE.set(true);
        }

        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    private static HttpServer startPythonAiStub() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext(
                    "/internal/v1/rag/collections",
                    InfrastructureIntegrationTest::handlePythonAiRequest
            );
            server.setExecutor(PYTHON_AI_EXECUTOR);
            server.start();
            return server;
        } catch (IOException exception) {
            throw new IllegalStateException("Could not start Python AI test stub", exception);
        }
    }

    private static void handlePythonAiRequest(HttpExchange exchange) throws IOException {
        String authorization = exchange.getRequestHeaders().getFirst("Authorization");
        String requestId = exchange.getRequestHeaders().getFirst(RequestIds.HEADER_NAME);
        boolean authorized = PYTHON_AI_AVAILABLE.get()
                && ("Bearer " + AI_SERVICE_TOKEN).equals(authorization)
                && requestId != null
                && requestId.length() >= 8;
        byte[] response = (
                authorized
                        ? "{\"requestId\":\"" + requestId + "\",\"collections\":[],\"rawResponseId\":null}"
                        : "{\"error\":{\"code\":\"SERVICE_UNAUTHORIZED\"}}"
        ).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        int status = PYTHON_AI_AVAILABLE.get() ? (authorized ? 200 : 401) : 503;
        exchange.sendResponseHeaders(status, response.length);
        exchange.getResponseBody().write(response);
        exchange.close();
    }
}
