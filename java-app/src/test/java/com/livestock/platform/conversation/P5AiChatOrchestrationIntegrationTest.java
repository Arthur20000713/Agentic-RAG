package com.livestock.platform.conversation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.ai.AiServiceProperties;
import com.livestock.platform.ai.context.RedisAiContextStore;
import com.livestock.platform.common.web.RequestIds;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
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
class P5AiChatOrchestrationIntegrationTest {

    private static final String ADMIN_USERNAME = "p5-admin";
    private static final String ADMIN_PASSWORD = "P5-admin-password-2026";
    private static final String CONTEXT_KEY_PREFIX = "p5:ai-context:";
    private static final FakeAiServer AI_SERVER = FakeAiServer.start();

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("livestock_app")
            .withUsername("livestock_app")
            .withPassword("p5-integration-password");

    @Container
    static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4-alpine")
            .withExposedPorts(6379);

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    RedisAiContextStore contextStore;

    @Autowired
    AiServiceProperties aiProperties;

    @MockitoSpyBean
    AuditService auditService;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", REDIS::getFirstMappedPort);
        registry.add(
                "livestock.security.jwt-secret",
                () -> "p5-integration-jwt-secret-at-least-32-characters"
        );
        registry.add("livestock.bootstrap-admin.enabled", () -> "true");
        registry.add("livestock.bootstrap-admin.username", () -> ADMIN_USERNAME);
        registry.add("livestock.bootstrap-admin.password", () -> ADMIN_PASSWORD);
        registry.add("livestock.ai-service.base-url", AI_SERVER::baseUrl);
        registry.add(
                "livestock.ai-service.service-token",
                () -> "p5-integration-service-token-at-least-32-characters"
        );
        registry.add("livestock.ai-service.chat-enabled", () -> "true");
        registry.add("livestock.ai-service.chat-read-timeout", () -> "100ms");
        registry.add("livestock.ai-context.key-prefix", () -> CONTEXT_KEY_PREFIX);
    }

    @BeforeEach
    void resetFakeAi() {
        AI_SERVER.reset();
    }

    @AfterEach
    void resetAuditSpy() {
        reset(auditService);
    }

    @AfterAll
    static void stopFakeAi() {
        AI_SERVER.stop();
    }

    @Test
    void twoSuccessfulTurnsUseBoundedOrderedHistoryAndVersionedRedisContext()
            throws Exception {
        Tokens user = createAndLoginUser("two-turns");
        String conversationId = createConversation(user, "Two successful turns");
        String firstOperation = "p5-first-" + UUID.randomUUID();
        String secondOperation = "p5-second-" + UUID.randomUUID();
        String firstQuestion = "First question about the cow";
        String secondQuestion = "Second question about the cow";

        JsonNode first = submit(
                user,
                conversationId,
                firstOperation,
                0,
                firstQuestion,
                "req-p5-first-" + UUID.randomUUID()
        );
        JsonNode second = submit(
                user,
                conversationId,
                secondOperation,
                1,
                secondQuestion,
                "req-p5-second-" + UUID.randomUUID()
        );

        assertThat(first.at("/task/status").asText()).isEqualTo("SUCCEEDED");
        assertThat(first.at("/assistantMessage/content").asText())
                .isEqualTo("answer-for-context-1");
        assertThat(second.at("/task/status").asText()).isEqualTo("SUCCEEDED");
        assertThat(second.at("/assistantMessage/content").asText())
                .isEqualTo("answer-for-context-2");

        List<JsonNode> requests = AI_SERVER.chatRequests();
        assertThat(requests).hasSize(2);
        assertThat(requests.get(0).path("history").size()).isZero();
        JsonNode secondRequest = requests.get(1);
        assertThat(secondRequest.path("query").asText()).isEqualTo(secondQuestion);
        assertThat(secondRequest.path("contextVersion").asLong()).isEqualTo(1);
        assertThat(secondRequest.at("/context/marker").asText())
                .isEqualTo("context-1");
        assertThat(secondRequest.path("history").size()).isEqualTo(2);
        assertThat(secondRequest.at("/history/0/role").asText()).isEqualTo("USER");
        assertThat(secondRequest.at("/history/0/content").asText())
                .isEqualTo(firstQuestion);
        assertThat(secondRequest.at("/history/1/role").asText())
                .isEqualTo("ASSISTANT");
        assertThat(secondRequest.at("/history/1/content").asText())
                .isEqualTo("answer-for-context-1");
        assertThat(secondRequest.path("history").findValuesAsText("content"))
                .doesNotContain(secondQuestion);

        long conversation = Long.parseLong(conversationId);
        long owner = Long.parseLong(user.userId());
        Map<String, Object> conversationState = jdbcTemplate.queryForMap(
                "SELECT context_version, active_operation_id "
                        + "FROM conversation WHERE id = ?",
                conversation
        );
        assertThat(((Number) conversationState.get("context_version")).longValue())
                .isEqualTo(2);
        assertThat(conversationState.get("active_operation_id")).isNull();
        assertSucceededTurn(conversation, firstOperation, "answer-for-context-1");
        assertSucceededTurn(conversation, secondOperation, "answer-for-context-2");

        JsonNode cachedEnvelope = objectMapper.readTree(
                redis.opsForValue().get(CONTEXT_KEY_PREFIX + owner + ":" + conversation)
        );
        assertThat(cachedEnvelope.path("contextVersion").asLong()).isEqualTo(2);
        assertThat(cachedEnvelope.at("/context/marker").asText())
                .isEqualTo("context-2");
        contextStore.put(
                owner,
                conversation,
                1,
                objectMapper.readTree("{\"schemaVersion\":1,\"marker\":\"stale\"}")
        );
        JsonNode afterStaleWrite = objectMapper.readTree(
                redis.opsForValue().get(CONTEXT_KEY_PREFIX + owner + ":" + conversation)
        );
        assertThat(afterStaleWrite.path("contextVersion").asLong()).isEqualTo(2);
        assertThat(afterStaleWrite.at("/context/marker").asText())
                .isEqualTo("context-2");
        assertThat(countAudit(first.at("/task/id").asText(), "AI_QUERY_COMPLETED"))
                .isOne();
        assertThat(countAudit(second.at("/task/id").asText(), "AI_QUERY_COMPLETED"))
                .isOne();

        long conversationVersion = jdbcTemplate.queryForObject(
                "SELECT version FROM conversation WHERE id = ?",
                Long.class,
                conversation
        );
        mockMvc.perform(
                        patch("/api/v1/conversations/{id}", conversationId)
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(user.accessToken())
                                )
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "status", "ARCHIVED",
                                        "version", conversationVersion
                                )))
                )
                .andExpect(status().isOk());
        assertThat(redis.hasKey(
                CONTEXT_KEY_PREFIX + owner + ":" + conversation
        )).isFalse();
    }

    @Test
    void lowConfidenceAndSafetyRefusalRemainSuccessfulWithoutSources()
            throws Exception {
        Tokens user = createAndLoginUser("guarded-outcomes");

        AI_SERVER.mode(FakeAiServer.Mode.LOW_CONFIDENCE);
        String lowConversation = createConversation(user, "Low confidence");
        JsonNode low = submit(
                user,
                lowConversation,
                "p5-low-confidence-" + UUID.randomUUID(),
                0,
                "Question without enough evidence",
                "req-p5-low-confidence-" + UUID.randomUUID()
        );
        assertThat(low.at("/task/status").asText()).isEqualTo("SUCCEEDED");
        assertThat(low.at("/assistantMessage/evidenceStatus").asText())
                .isEqualTo("LOW_CONFIDENCE");
        assertThat(low.at("/assistantMessage/metadata/outcome").asText())
                .isEqualTo("LOW_CONFIDENCE");
        assertThat(low.at("/assistantMessage/metadata/sources").isEmpty())
                .isTrue();

        AI_SERVER.mode(FakeAiServer.Mode.SAFETY_REFUSAL);
        String safetyConversation = createConversation(user, "Safety refusal");
        JsonNode refused = submit(
                user,
                safetyConversation,
                "p5-safety-refusal-" + UUID.randomUUID(),
                0,
                "Unsafe request",
                "req-p5-safety-refusal-" + UUID.randomUUID()
        );
        assertThat(refused.at("/task/status").asText()).isEqualTo("SUCCEEDED");
        assertThat(refused.at("/assistantMessage/evidenceStatus").asText())
                .isEqualTo("NOT_REQUIRED");
        assertThat(refused.at("/assistantMessage/metadata/outcome").asText())
                .isEqualTo("SAFETY_REFUSAL");
        assertThat(refused.at("/assistantMessage/metadata/safety/decision").asText())
                .isEqualTo("REFUSED");
        assertThat(refused.at("/assistantMessage/metadata/sources").isEmpty())
                .isTrue();
    }

    @Test
    void responseLossReconcilesSucceededRunAndPersistsOneAssistantMessage()
            throws Exception {
        AI_SERVER.mode(FakeAiServer.Mode.TIMEOUT_AFTER_PERSIST);
        Tokens user = createAndLoginUser("response-loss");
        String conversationId = createConversation(user, "Response loss");
        String operationId = "p5-lost-response-" + UUID.randomUUID();

        JsonNode result = submit(
                user,
                conversationId,
                operationId,
                0,
                "Question whose POST response is lost",
                "req-p5-lost-" + UUID.randomUUID()
        );

        assertThat(result.at("/task/status").asText()).isEqualTo("SUCCEEDED");
        assertThat(result.at("/assistantMessage/content").asText())
                .isEqualTo("answer-for-context-1");
        assertThat(AI_SERVER.postCalls()).isOne();
        assertThat(AI_SERVER.runCalls()).isOne();
        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message "
                        + "WHERE conversation_id = ? AND turn_id = ? "
                        + "AND role = 'ASSISTANT'",
                Long.parseLong(conversationId),
                operationId
        )).isOne();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT status FROM biz_task WHERE operation_id = ?",
                String.class,
                operationId
        )).isEqualTo("SUCCEEDED");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM audit_log "
                        + "WHERE resource_id = ? "
                        + "AND action = 'AI_QUERY_SUBMISSION_UNKNOWN'",
                Integer.class,
                result.at("/task/id").asText()
        )).isOne();
        assertThat(countAudit(
                result.at("/task/id").asText(),
                "AI_QUERY_COMPLETED"
        )).isOne();
    }

    @Test
    void malformedSuccessfulPostIsReconciledFromDurableRun() throws Exception {
        AI_SERVER.mode(FakeAiServer.Mode.MALFORMED_AFTER_PERSIST);
        Tokens user = createAndLoginUser("malformed-success");
        String conversationId = createConversation(user, "Malformed success");
        String operationId = "p5-malformed-success-" + UUID.randomUUID();

        JsonNode result = submit(
                user,
                conversationId,
                operationId,
                0,
                "Question with malformed POST response",
                "req-p5-malformed-" + UUID.randomUUID()
        );

        assertThat(result.at("/task/status").asText()).isEqualTo("SUCCEEDED");
        assertThat(result.at("/assistantMessage/content").asText())
                .isEqualTo("answer-for-context-1");
        assertThat(AI_SERVER.postCalls()).isOne();
        assertThat(AI_SERVER.runCalls()).isOne();
    }

    @Test
    void idempotentReplayRecoversCrashBeforePythonClaim() throws Exception {
        AI_SERVER.mode(FakeAiServer.Mode.LOSE_BEFORE_PERSIST_ONCE);
        Tokens user = createAndLoginUser("pre-dispatch-crash");
        String conversationId = createConversation(user, "Pre-dispatch crash");
        String operationId = "p5-pre-dispatch-" + UUID.randomUUID();
        String requestId = "req-p5-pre-dispatch-" + UUID.randomUUID();
        String payload = json(Map.of(
                "content", "Question recovered with the same operation",
                "contextVersion", 0
        ));

        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", operationId)
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(payload)
                )
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.task.status").value("SUBMIT_UNKNOWN"));

        MvcResult replay = mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", operationId)
                                .header(RequestIds.HEADER_NAME, "req-replay-" + UUID.randomUUID())
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(payload)
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.task.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.data.assistantMessage.content")
                        .value("answer-for-context-1"))
                .andExpect(header().string("Idempotent-Replayed", "true"))
                .andReturn();

        assertThat(body(replay).at("/data/task/status").asText())
                .isEqualTo("SUCCEEDED");
        assertThat(AI_SERVER.postCalls()).isEqualTo(2);
        assertThat(AI_SERVER.runCalls()).isEqualTo(2);
        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message "
                        + "WHERE conversation_id = ? AND turn_id = ? AND role = 'ASSISTANT'",
                Long.parseLong(conversationId),
                operationId
        )).isOne();
    }

    @Test
    void disabledChatRejectsBeforeClaimingConversation() throws Exception {
        Tokens user = createAndLoginUser("disabled-preflight");
        String conversationId = createConversation(user, "Disabled preflight");
        String operationId = "p5-disabled-" + UUID.randomUUID();
        aiProperties.setChatEnabled(false);
        try {
            mockMvc.perform(
                            post("/api/v1/conversations/{id}/messages", conversationId)
                                    .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                    .header("Idempotency-Key", operationId)
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .content(json(Map.of(
                                            "content", "Must not be persisted",
                                            "contextVersion", 0
                                    )))
                    )
                    .andExpect(status().isServiceUnavailable())
                    .andExpect(jsonPath("$.error.code").value("AI_CHAT_DISABLED"));
        } finally {
            aiProperties.setChatEnabled(true);
        }

        assertThat(count(
                "SELECT COUNT(*) FROM biz_task WHERE operation_id = ?",
                operationId
        )).isZero();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT active_operation_id FROM conversation WHERE id = ?",
                String.class,
                Long.parseLong(conversationId)
        )).isNull();
    }

    @Test
    void completionAuditFailureRollsBackTransactionBAndSkipsRedisWrite()
            throws Exception {
        Tokens user = createAndLoginUser("audit-rollback");
        String conversationId = createConversation(user, "Completion rollback");
        String operationId = "p5-audit-failure-" + UUID.randomUUID();
        String requestId = "req-p5-audit-failure-" + UUID.randomUUID();
        doThrow(new IllegalStateException("forced AI_QUERY_COMPLETED audit failure"))
                .when(auditService)
                .append(argThat(event ->
                        "AI_QUERY_COMPLETED".equals(event.action())
                ));

        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(user.accessToken())
                                )
                                .header("Idempotency-Key", operationId)
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "This completion must roll back",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.error.code").value("INTERNAL_ERROR"));

        long conversation = Long.parseLong(conversationId);
        Map<String, Object> conversationState = jdbcTemplate.queryForMap(
                "SELECT context_version, active_operation_id "
                        + "FROM conversation WHERE id = ?",
                conversation
        );
        assertThat(((Number) conversationState.get("context_version")).longValue())
                .isZero();
        assertThat(conversationState.get("active_operation_id"))
                .isEqualTo(operationId);
        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message "
                        + "WHERE conversation_id = ? AND turn_id = ? "
                        + "AND role = 'ASSISTANT'",
                conversation,
                operationId
        )).isZero();
        Map<String, Object> taskState = jdbcTemplate.queryForMap(
                "SELECT id, status, progress, executor_job_id, result_ref "
                        + "FROM biz_task WHERE operation_id = ?",
                operationId
        );
        assertThat(taskState.get("status")).isEqualTo("RUNNING");
        assertThat(((Number) taskState.get("progress")).intValue()).isEqualTo(10);
        assertThat(taskState.get("executor_job_id")).isNull();
        assertThat(taskState.get("result_ref")).isNull();
        assertThat(countAudit(
                String.valueOf(taskState.get("id")),
                "AI_QUERY_COMPLETED"
        )).isZero();
        assertThat(redis.hasKey(
                CONTEXT_KEY_PREFIX + user.userId() + ":" + conversationId
        )).isFalse();

        reset(auditService);
        MvcResult recovered = mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", operationId)
                                .header(RequestIds.HEADER_NAME, "req-recover-" + UUID.randomUUID())
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "This completion must roll back",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isOk())
                .andExpect(header().string("Idempotent-Replayed", "true"))
                .andExpect(jsonPath("$.data.task.status").value("SUCCEEDED"))
                .andReturn();
        assertThat(body(recovered).at("/data/assistantMessage/content").asText())
                .isEqualTo("answer-for-context-1");
        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message "
                        + "WHERE conversation_id = ? AND turn_id = ? AND role = 'ASSISTANT'",
                conversation,
                operationId
        )).isOne();
        assertThat(countAudit(
                String.valueOf(taskState.get("id")),
                "AI_QUERY_COMPLETED"
        )).isOne();
    }

    private void assertSucceededTurn(
            long conversationId,
            String operationId,
            String expectedAnswer
    ) {
        Map<String, Object> task = jdbcTemplate.queryForMap(
                "SELECT id, status, progress, executor_job_id, result_ref, error_code "
                        + "FROM biz_task WHERE operation_id = ?",
                operationId
        );
        assertThat(task.get("status")).isEqualTo("SUCCEEDED");
        assertThat(((Number) task.get("progress")).intValue()).isEqualTo(100);
        assertThat(task.get("executor_job_id")).isNotNull();
        assertThat(String.valueOf(task.get("result_ref"))).startsWith("message:");
        assertThat(task.get("error_code")).isNull();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT content FROM conversation_message "
                        + "WHERE conversation_id = ? AND turn_id = ? "
                        + "AND role = 'ASSISTANT'",
                String.class,
                conversationId,
                operationId
        )).isEqualTo(expectedAnswer);
    }

    private JsonNode submit(
            Tokens user,
            String conversationId,
            String operationId,
            long contextVersion,
            String content,
            String requestId
    ) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(user.accessToken())
                                )
                                .header("Idempotency-Key", operationId)
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", content,
                                        "contextVersion", contextVersion
                                )))
                )
                .andExpect(status().isOk())
                .andReturn();
        return body(result).path("data");
    }

    private String createConversation(Tokens user, String title) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/conversations")
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(user.accessToken())
                                )
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of("title", title)))
                )
                .andExpect(status().isCreated())
                .andReturn();
        return body(result).at("/data/id").asText();
    }

    private Tokens createAndLoginUser(String label) throws Exception {
        String suffix = UUID.randomUUID().toString().substring(0, 8);
        String username = "p5-" + label + "-" + suffix;
        String password = "P5-password-" + suffix;
        Tokens admin = login(ADMIN_USERNAME, ADMIN_PASSWORD);
        mockMvc.perform(
                        post("/api/v1/users")
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(admin.accessToken())
                                )
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", username,
                                        "password", password,
                                        "roles", new String[]{"USER"}
                                )))
                )
                .andExpect(status().isCreated());
        return login(username, password);
    }

    private Tokens login(String username, String password) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/auth/login")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", username,
                                        "password", password
                                )))
                )
                .andExpect(status().isOk())
                .andReturn();
        JsonNode data = body(result).path("data");
        return new Tokens(
                data.path("accessToken").asText(),
                data.path("user").path("id").asText()
        );
    }

    private int countAudit(String taskId, String action) {
        return jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM audit_log "
                        + "WHERE resource_type = 'TASK' "
                        + "AND resource_id = ? AND action = ?",
                Integer.class,
                taskId,
                action
        );
    }

    private int count(String sql, Object... parameters) {
        return jdbcTemplate.queryForObject(sql, Integer.class, parameters);
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

    private record Tokens(String accessToken, String userId) {
    }

    private static final class FakeAiServer {

        private enum Mode {
            SUCCESS,
            TIMEOUT_AFTER_PERSIST,
            MALFORMED_AFTER_PERSIST,
            LOSE_BEFORE_PERSIST_ONCE,
            LOW_CONFIDENCE,
            SAFETY_REFUSAL
        }

        private final ObjectMapper objectMapper =
                new ObjectMapper().findAndRegisterModules();
        private final HttpServer server;
        private final ExecutorService executor;
        private final AtomicReference<Mode> mode =
                new AtomicReference<>(Mode.SUCCESS);
        private final List<JsonNode> chatRequests = new CopyOnWriteArrayList<>();
        private final Map<String, JsonNode> runs =
                new java.util.concurrent.ConcurrentHashMap<>();
        private final AtomicInteger postCalls = new AtomicInteger();
        private final AtomicInteger runCalls = new AtomicInteger();

        private FakeAiServer() throws IOException {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            executor = Executors.newCachedThreadPool();
            server.setExecutor(executor);
            server.createContext("/internal/v1/ai/chat", this::chat);
            server.createContext("/internal/v1/ai/runs/", this::run);
            server.start();
        }

        static FakeAiServer start() {
            try {
                return new FakeAiServer();
            } catch (IOException exception) {
                throw new ExceptionInInitializerError(exception);
            }
        }

        String baseUrl() {
            return "http://127.0.0.1:" + server.getAddress().getPort();
        }

        void mode(Mode nextMode) {
            mode.set(nextMode);
        }

        List<JsonNode> chatRequests() {
            return List.copyOf(chatRequests);
        }

        int postCalls() {
            return postCalls.get();
        }

        int runCalls() {
            return runCalls.get();
        }

        void reset() {
            mode.set(Mode.SUCCESS);
            chatRequests.clear();
            runs.clear();
            postCalls.set(0);
            runCalls.set(0);
        }

        void stop() {
            server.stop(0);
            executor.shutdownNow();
        }

        private void chat(HttpExchange exchange) throws IOException {
            postCalls.incrementAndGet();
            JsonNode request = objectMapper.readTree(exchange.getRequestBody());
            chatRequests.add(request.deepCopy());
            if (mode.compareAndSet(Mode.LOSE_BEFORE_PERSIST_ONCE, Mode.SUCCESS)) {
                exchange.close();
                return;
            }
            JsonNode response = responseFor(request);
            runs.put(request.path("operationId").asText(), response);
            if (mode.get() == Mode.TIMEOUT_AFTER_PERSIST) {
                try {
                    Thread.sleep(350);
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
            }
            JsonNode responseBody = mode.get() == Mode.MALFORMED_AFTER_PERSIST
                    ? objectMapper.createObjectNode().put("malformed", true)
                    : response;
            respond(
                    exchange,
                    200,
                    responseBody,
                    request.path("requestId").asText()
            );
        }

        private void run(HttpExchange exchange) throws IOException {
            runCalls.incrementAndGet();
            String path = exchange.getRequestURI().getPath();
            String operationId = path.substring(path.lastIndexOf('/') + 1);
            JsonNode result = runs.get(operationId);
            String requestId = exchange.getRequestHeaders()
                    .getFirst(RequestIds.HEADER_NAME);
            if (result == null) {
                ObjectNode missing = objectMapper.createObjectNode();
                missing.put("requestId", requestId);
                missing.put("operationId", operationId);
                ObjectNode error = missing.putObject("error");
                error.put("code", "OPERATION_NOT_FOUND");
                error.put("message", "operation not found");
                error.put("retryable", false);
                error.putObject("details");
                respond(exchange, 404, missing, requestId);
                return;
            }
            OffsetDateTime now = OffsetDateTime.now();
            ObjectNode run = objectMapper.createObjectNode();
            run.put("requestId", requestId);
            run.put("operationId", operationId);
            run.put("runId", result.path("runId").asText());
            run.put("type", "AI_CHAT");
            run.put("status", "SUCCEEDED");
            run.set("result", result);
            run.putNull("error");
            run.put("createdAt", now.minusSeconds(1).toString());
            run.put("updatedAt", now.toString());
            run.put("expiresAt", now.plusHours(1).toString());
            respond(exchange, 200, run, requestId);
        }

        private JsonNode responseFor(JsonNode request) {
            long nextVersion = request.path("contextVersion").asLong() + 1;
            ObjectNode response = objectMapper.createObjectNode();
            response.put("requestId", request.path("requestId").asText());
            response.put("operationId", request.path("operationId").asText());
            response.put(
                    "runId",
                    "run-" + request.path("operationId").asText()
            );
            Mode currentMode = mode.get();
            response.put(
                    "outcome",
                    currentMode == Mode.LOW_CONFIDENCE
                            ? "LOW_CONFIDENCE"
                            : currentMode == Mode.SAFETY_REFUSAL
                            ? "SAFETY_REFUSAL"
                            : "ANSWERED"
            );
            response.put(
                    "answer",
                    currentMode == Mode.LOW_CONFIDENCE
                            ? "Insufficient evidence for a reliable answer"
                            : currentMode == Mode.SAFETY_REFUSAL
                            ? "This request cannot be answered safely"
                            : "answer-for-context-" + nextVersion
            );
            response.put("intent", "disease_consultation");
            response.put("riskLevel", "MEDIUM");
            response.put(
                    "evidenceStatus",
                    currentMode == Mode.LOW_CONFIDENCE
                            ? "LOW_CONFIDENCE"
                            : currentMode == Mode.SAFETY_REFUSAL
                            ? "NOT_REQUIRED"
                            : "SUPPORTED"
            );
            response.putArray("sources");
            response.putArray("followUpQuestions");
            response.putArray("toolsUsed").add("query_knowledge_hub");
            ObjectNode safety = response.putObject("safety");
            safety.put(
                    "decision",
                    currentMode == Mode.SAFETY_REFUSAL ? "REFUSED" : "ALLOWED"
            );
            if (currentMode == Mode.SAFETY_REFUSAL) {
                safety.put("reasonCode", "POLICY_REFUSAL");
            } else {
                safety.putNull("reasonCode");
            }
            ObjectNode nextContext = response.putObject("nextContext");
            nextContext.put("schemaVersion", 1);
            nextContext.put("marker", "context-" + nextVersion);
            response.put("contextVersion", nextVersion);
            response.put(
                    "traceId",
                    "trace-" + request.path("operationId").asText()
            );
            return response;
        }

        private void respond(
                HttpExchange exchange,
                int status,
                JsonNode body,
                String requestId
        ) throws IOException {
            byte[] bytes = objectMapper.writeValueAsString(body)
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    HttpHeaders.CONTENT_TYPE,
                    MediaType.APPLICATION_JSON_VALUE
            );
            exchange.getResponseHeaders().set(RequestIds.HEADER_NAME, requestId);
            exchange.sendResponseHeaders(status, bytes.length);
            try {
                exchange.getResponseBody().write(bytes);
            } finally {
                exchange.close();
            }
        }
    }
}
