package com.livestock.platform.conversation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.conversation.api.ConversationController;
import com.livestock.platform.conversation.service.AiChatOrchestrationService;
import com.livestock.platform.audit.AuditService;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
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
class P4ConversationTaskIntegrationTest {

    private static final String ADMIN_USERNAME = "p4-admin";
    private static final String ADMIN_PASSWORD = "P4-admin-password-2026";

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("livestock_app")
            .withUsername("livestock_app")
            .withPassword("p4-integration-password");

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

    @MockitoSpyBean
    AiChatOrchestrationService aiChatOrchestrationService;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", REDIS::getFirstMappedPort);
        registry.add(
                "livestock.security.jwt-secret",
                () -> "p4-integration-jwt-secret-at-least-32-characters"
        );
        registry.add("livestock.bootstrap-admin.enabled", () -> "true");
        registry.add("livestock.bootstrap-admin.username", () -> ADMIN_USERNAME);
        registry.add("livestock.bootstrap-admin.password", () -> ADMIN_PASSWORD);
        registry.add("livestock.ai-service.chat-enabled", () -> "true");
    }

    @BeforeEach
    void bypassSynchronousAiForP4ContractTests() {
        doAnswer(invocation -> invocation.getArgument(0))
                .when(aiChatOrchestrationService)
                .execute(any(), any(), any());
    }

    @Test
    void conversationLifecycleUsesOptimisticVersionAndSoftDelete() throws Exception {
        Tokens user = createAndLoginUser("lifecycle", "USER");
        JsonNode created = createConversation(user, "Initial title");
        String id = created.path("id").asText();
        long initialVersion = created.path("version").asLong();

        mockMvc.perform(
                        get("/api/v1/conversations")
                                .param("scope", "own")
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.items[0].id").value(id));

        MvcResult renamedResult = mockMvc.perform(
                        patch("/api/v1/conversations/{id}", id)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "title", "Renamed title",
                                        "version", initialVersion
                                )))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.title").value("Renamed title"))
                .andReturn();
        long renamedVersion = body(renamedResult).at("/data/version").asLong();

        mockMvc.perform(
                        patch("/api/v1/conversations/{id}", id)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "status", "ARCHIVED",
                                        "version", initialVersion
                                )))
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("VERSION_CONFLICT"));

        MvcResult archivedResult = mockMvc.perform(
                        patch("/api/v1/conversations/{id}", id)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "status", "ARCHIVED",
                                        "version", renamedVersion
                                )))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("ARCHIVED"))
                .andReturn();
        long archivedVersion = body(archivedResult).at("/data/version").asLong();

        mockMvc.perform(
                        delete("/api/v1/conversations/{id}", id)
                                .param("version", String.valueOf(archivedVersion))
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                )
                .andExpect(status().isNoContent());

        mockMvc.perform(
                        get("/api/v1/conversations/{id}", id)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("CONVERSATION_NOT_FOUND"));
        mockMvc.perform(
                        delete("/api/v1/conversations/{id}", id)
                                .param("version", String.valueOf(archivedVersion))
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("CONVERSATION_NOT_FOUND"));

        assertThat(jdbcTemplate.queryForObject(
                "SELECT status FROM conversation WHERE id = ?",
                String.class,
                Long.valueOf(id)
        )).isEqualTo("DELETED");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM audit_log WHERE resource_type = 'CONVERSATION' "
                        + "AND resource_id = ?",
                Integer.class,
                id
        )).isEqualTo(4);
    }

    @Test
    void authorizationReturns403WithoutPermissionAnd404ForCrossOwnerResources()
            throws Exception {
        Tokens owner = createAndLoginUser("owner", "USER");
        Tokens other = createAndLoginUser("other", "USER");
        Tokens auditor = createAndLoginUser("auditor", "AUDITOR");
        JsonNode created = createConversation(owner, "Private");
        String id = created.path("id").asText();

        mockMvc.perform(
                        get("/api/v1/conversations/{id}", id)
                                .header(HttpHeaders.AUTHORIZATION, bearer(auditor.accessToken()))
                )
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("ACCESS_DENIED"));

        mockMvc.perform(
                        get("/api/v1/conversations/{id}", id)
                                .header(HttpHeaders.AUTHORIZATION, bearer(other.accessToken()))
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("CONVERSATION_NOT_FOUND"));

        mockMvc.perform(
                        patch("/api/v1/conversations/{id}", id)
                                .header(HttpHeaders.AUTHORIZATION, bearer(other.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "title", "Stolen",
                                        "version", created.path("version").asLong()
                                )))
                )
                .andExpect(status().isNotFound());
    }

    @Test
    void messageSubmissionIsDurableAtomicAndIdempotent() throws Exception {
        Tokens user = createAndLoginUser("idempotent", "USER");
        String conversationId = createConversation(user, "Idempotency")
                .path("id").asText();
        String key = "p4-operation-" + UUID.randomUUID();
        String requestId = "req-p4-submit-" + UUID.randomUUID();
        String conflictRequestId = "req-p4-conflict-" + UUID.randomUUID();
        String payload = json(Map.of(
                "content", "The cow has a fever.",
                "contextVersion", 0
        ));

        MvcResult first = mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", key)
                                .header(RequestIds.HEADER_NAME, requestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(payload)
                )
                .andExpect(status().isAccepted())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andExpect(header().doesNotExist(
                        ConversationController.IDEMPOTENT_REPLAYED
                ))
                .andExpect(jsonPath("$.data.replayed").value(false))
                .andExpect(jsonPath("$.data.task.status").value("CREATED"))
                .andReturn();
        JsonNode firstData = body(first).path("data");

        MvcResult replay = mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", key)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(payload)
                )
                .andExpect(status().isOk())
                .andExpect(header().string(
                        ConversationController.IDEMPOTENT_REPLAYED,
                        "true"
                ))
                .andExpect(jsonPath("$.data.replayed").value(true))
                .andReturn();
        JsonNode replayData = body(replay).path("data");
        assertThat(replayData.at("/message/id").asText())
                .isEqualTo(firstData.at("/message/id").asText());
        assertThat(replayData.at("/task/id").asText())
                .isEqualTo(firstData.at("/task/id").asText());

        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", key)
                                .header(RequestIds.HEADER_NAME, conflictRequestId)
                                .header(HttpHeaders.USER_AGENT, "p4-conflict-client/1.0")
                                .with(request -> {
                                    request.setRemoteAddr("203.0.113.77");
                                    return request;
                                })
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "Different payload",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("IDEMPOTENCY_KEY_REUSED"));

        assertThat(count(
                "SELECT COUNT(*) FROM biz_task WHERE operation_id = ?",
                key
        )).isOne();
        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message WHERE turn_id = ?",
                key
        )).isOne();
        assertThat(count(
                "SELECT COUNT(*) FROM audit_log WHERE request_id = ? "
                        + "AND action = 'AI_QUERY_SUBMITTED'",
                requestId
        )).isOne();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT JSON_UNQUOTE(JSON_EXTRACT(detail_json, "
                        + "'$.idempotencyKeyDigest')) FROM audit_log "
                        + "WHERE request_id = ?",
                String.class,
                requestId
        )).doesNotContain(key);
        assertThat(jdbcTemplate.queryForMap(
                "SELECT client_ip, user_agent FROM audit_log "
                        + "WHERE request_id = ? AND action = 'IDEMPOTENCY_CONFLICT'",
                conflictRequestId
        )).containsEntry("client_ip", "203.0.113.77")
                .containsEntry("user_agent", "p4-conflict-client/1.0");
    }

    @Test
    void requestIdIsCorrelationMetadataAndCanBeReusedAcrossMessages()
            throws Exception {
        Tokens user = createAndLoginUser("request-id", "USER");
        String firstConversation = createConversation(user, "First request ID")
                .path("id").asText();
        String secondConversation = createConversation(user, "Second request ID")
                .path("id").asText();
        String sharedRequestId = "req-p4-shared-" + UUID.randomUUID();

        mockMvc.perform(
                        post(
                                "/api/v1/conversations/{id}/messages",
                                firstConversation
                        )
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(user.accessToken())
                                )
                                .header("Idempotency-Key", "first-" + UUID.randomUUID())
                                .header(RequestIds.HEADER_NAME, sharedRequestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "First independent request",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isAccepted());
        mockMvc.perform(
                        post(
                                "/api/v1/conversations/{id}/messages",
                                secondConversation
                        )
                                .header(
                                        HttpHeaders.AUTHORIZATION,
                                        bearer(user.accessToken())
                                )
                                .header("Idempotency-Key", "second-" + UUID.randomUUID())
                                .header(RequestIds.HEADER_NAME, sharedRequestId)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "Second independent request",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isAccepted());

        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message WHERE request_id = ?",
                sharedRequestId
        )).isEqualTo(2);
    }

    @Test
    void busyArchivedAndContextConflictsAreStable() throws Exception {
        Tokens user = createAndLoginUser("conflict", "USER");
        JsonNode busy = createConversation(user, "Busy");
        submit(user, busy.path("id").asText(), "busy-first", 0, "first")
                .andExpect(status().isAccepted());
        submit(user, busy.path("id").asText(), "busy-second", 0, "second")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("CONVERSATION_BUSY"));

        JsonNode stale = createConversation(user, "Stale context");
        submit(user, stale.path("id").asText(), "stale-context", 1, "question")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("CONTEXT_VERSION_CONFLICT"));

        JsonNode archived = createConversation(user, "Archived");
        String archivedId = archived.path("id").asText();
        mockMvc.perform(
                        patch("/api/v1/conversations/{id}", archivedId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "status", "ARCHIVED",
                                        "version", archived.path("version").asLong()
                                )))
                )
                .andExpect(status().isOk());
        submit(user, archivedId, "archived-submit", 0, "question")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("CONVERSATION_NOT_ACTIVE"));
    }

    @Test
    void concurrentReplayCreatesExactlyOneMessageAndTask() throws Exception {
        Tokens user = createAndLoginUser("concurrent", "USER");
        String conversationId = createConversation(user, "Concurrent")
                .path("id").asText();
        String key = "concurrent-" + UUID.randomUUID();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        List<Callable<ConcurrentResult>> calls = List.of(
                () -> concurrentSubmit(user, conversationId, key, ready, start),
                () -> concurrentSubmit(user, conversationId, key, ready, start)
        );
        List<Future<ConcurrentResult>> futures = new ArrayList<>();
        try {
            calls.forEach(call -> futures.add(executor.submit(call)));
            ready.await();
            start.countDown();
            List<ConcurrentResult> results = List.of(
                    futures.get(0).get(),
                    futures.get(1).get()
            );
            assertThat(results)
                    .withFailMessage("concurrent responses were %s", results)
                    .extracting(ConcurrentResult::status)
                    .containsExactlyInAnyOrder(202, 200);
        } finally {
            executor.shutdownNow();
        }
        assertThat(count(
                "SELECT COUNT(*) FROM biz_task WHERE operation_id = ?",
                key
        )).isOne();
        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message WHERE turn_id = ?",
                key
        )).isOne();
    }

    @Test
    void concurrentSameKeyAcrossConversationsReturnsOneStableConflict()
            throws Exception {
        Tokens user = createAndLoginUser("cross-conversation", "USER");
        String firstConversation = createConversation(user, "First")
                .path("id").asText();
        String secondConversation = createConversation(user, "Second")
                .path("id").asText();
        String key = "cross-conversation-" + UUID.randomUUID();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<ConcurrentResult> first = executor.submit(
                    () -> concurrentSubmit(
                            user,
                            firstConversation,
                            key,
                            "first payload",
                            ready,
                            start
                    )
            );
            Future<ConcurrentResult> second = executor.submit(
                    () -> concurrentSubmit(
                            user,
                            secondConversation,
                            key,
                            "second payload",
                            ready,
                            start
                    )
            );
            ready.await();
            start.countDown();
            List<ConcurrentResult> results = List.of(first.get(), second.get());
            assertThat(results)
                    .extracting(ConcurrentResult::status)
                    .containsExactlyInAnyOrder(202, 409);
            ConcurrentResult conflict = results.stream()
                    .filter(result -> result.status() == 409)
                    .findFirst()
                    .orElseThrow();
            assertThat(conflict.body()).contains("IDEMPOTENCY_KEY_REUSED");
        } finally {
            executor.shutdownNow();
        }
        assertThat(count(
                "SELECT COUNT(*) FROM biz_task WHERE operation_id = ?",
                key
        )).isOne();
        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message WHERE turn_id = ?",
                key
        )).isOne();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM conversation "
                        + "WHERE id IN (?, ?) AND active_operation_id IS NULL",
                Integer.class,
                Long.valueOf(firstConversation),
                Long.valueOf(secondConversation)
        )).isOne();
    }

    @Test
    void auditFailureRollsBackConversationClaimTaskAndMessage() throws Exception {
        Tokens user = createAndLoginUser("rollback", "USER");
        String conversationId = createConversation(user, "Rollback")
                .path("id").asText();
        String key = "rollback-" + UUID.randomUUID();
        doThrow(new IllegalStateException("forced audit failure"))
                .when(auditService)
                .append(argThat(event -> "AI_QUERY_SUBMITTED".equals(event.action())));
        try {
            submit(user, conversationId, key, 0, "must roll back")
                    .andExpect(status().isInternalServerError())
                    .andExpect(jsonPath("$.error.code").value("INTERNAL_ERROR"));
        } finally {
            reset(auditService);
        }

        Map<String, Object> conversation = jdbcTemplate.queryForMap(
                """
                SELECT active_operation_id, context_version, version, last_message_at
                FROM conversation
                WHERE id = ?
                """,
                Long.valueOf(conversationId)
        );
        assertThat(conversation.get("active_operation_id")).isNull();
        assertThat(((Number) conversation.get("context_version")).longValue()).isZero();
        assertThat(((Number) conversation.get("version")).longValue()).isZero();
        assertThat(conversation.get("last_message_at")).isNull();
        assertThat(count(
                "SELECT COUNT(*) FROM biz_task WHERE operation_id = ?",
                key
        )).isZero();
        assertThat(count(
                "SELECT COUNT(*) FROM conversation_message WHERE turn_id = ?",
                key
        )).isZero();
    }

    @Test
    void boundedHistoryUsesStableCreatedAtAndIdOrdering() throws Exception {
        Tokens user = createAndLoginUser("history", "USER");
        String conversationId = createConversation(user, "History")
                .path("id").asText();
        Instant timestamp = Instant.parse("2026-07-30T01:02:03Z");
        List<Long> ids = new ArrayList<>();
        for (int index = 1; index <= 5; index++) {
            jdbcTemplate.update(
                    """
                    INSERT INTO conversation_message(
                        conversation_id, turn_id, role, content, request_id,
                        status, metadata_json, created_at
                    ) VALUES (?, ?, 'USER', ?, ?, 'COMPLETED', JSON_OBJECT(), ?)
                    """,
                    Long.valueOf(conversationId),
                    "history-turn-" + index,
                    "message-" + index,
                    "history-request-" + UUID.randomUUID(),
                    timestamp
            );
            ids.add(jdbcTemplate.queryForObject(
                    "SELECT LAST_INSERT_ID()",
                    Long.class
            ));
        }

        MvcResult result = mockMvc.perform(
                        get("/api/v1/conversations/{id}/messages", conversationId)
                                .param("limit", "3")
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(3))
                .andReturn();
        JsonNode messages = body(result).path("data");
        assertThat(messages.get(0).path("id").asLong()).isEqualTo(ids.get(2));
        assertThat(messages.get(1).path("id").asLong()).isEqualTo(ids.get(3));
        assertThat(messages.get(2).path("id").asLong()).isEqualTo(ids.get(4));
    }

    @Test
    void taskQueriesRespectOwnershipAndAdminScope() throws Exception {
        Tokens owner = createAndLoginUser("task-owner", "USER");
        Tokens other = createAndLoginUser("task-other", "USER");
        Tokens admin = login(ADMIN_USERNAME, ADMIN_PASSWORD);
        String conversationId = createConversation(owner, "Task owner")
                .path("id").asText();
        MvcResult submitted = submit(
                owner,
                conversationId,
                "task-query-" + UUID.randomUUID(),
                0,
                "question"
        ).andExpect(status().isAccepted()).andReturn();
        String taskId = body(submitted).at("/data/task/id").asText();

        mockMvc.perform(
                        get("/api/v1/tasks/{id}", taskId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(owner.accessToken()))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.id").value(taskId));
        mockMvc.perform(
                        get("/api/v1/tasks/{id}", taskId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(other.accessToken()))
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("TASK_NOT_FOUND"));
        mockMvc.perform(
                        get("/api/v1/tasks")
                                .param("scope", "all")
                                .header(HttpHeaders.AUTHORIZATION, bearer(owner.accessToken()))
                )
                .andExpect(status().isForbidden());
        mockMvc.perform(
                        get("/api/v1/tasks")
                                .param("scope", "all")
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.totalElements").value(
                        org.hamcrest.Matchers.greaterThanOrEqualTo(1)
                ));
    }

    @Test
    void requiredVersionsAndIdempotencyHeaderCannotBeOmitted() throws Exception {
        Tokens user = createAndLoginUser("validation", "USER");
        String conversationId = createConversation(user, "Validation")
                .path("id").asText();

        mockMvc.perform(
                        patch("/api/v1/conversations/{id}", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of("title", "No version")))
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "No key",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", "missing-context-version")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of("content", "No context version")))
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", "short")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "Invalid operation key",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", "invalid key spaces")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "Invalid operation key",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header(
                                        "Idempotency-Key",
                                        "content-too-long-" + UUID.randomUUID()
                                )
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "x".repeat(4001),
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
    }

    @Test
    void conversationAndTaskPathIdsMustBePositive() throws Exception {
        Tokens user = createAndLoginUser("positive-path-id", "USER");
        String authorization = bearer(user.accessToken());

        mockMvc.perform(
                        get("/api/v1/conversations/{id}", 0)
                                .header(HttpHeaders.AUTHORIZATION, authorization)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        get("/api/v1/conversations/{id}/messages", -1)
                                .header(HttpHeaders.AUTHORIZATION, authorization)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        patch("/api/v1/conversations/{id}", 0)
                                .header(HttpHeaders.AUTHORIZATION, authorization)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of("title", "Invalid id", "version", 0)))
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        delete("/api/v1/conversations/{id}", -1)
                                .param("version", "0")
                                .header(HttpHeaders.AUTHORIZATION, authorization)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", 0)
                                .header(HttpHeaders.AUTHORIZATION, authorization)
                                .header("Idempotency-Key", "invalid-path-id")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", "Invalid path id",
                                        "contextVersion", 0
                                )))
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
        mockMvc.perform(
                        get("/api/v1/tasks/{id}", -1)
                                .header(HttpHeaders.AUTHORIZATION, authorization)
                )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("VALIDATION_FAILED"));
    }

    private ConcurrentResult concurrentSubmit(
            Tokens user,
            String conversationId,
            String key,
            CountDownLatch ready,
            CountDownLatch start
    ) throws Exception {
        return concurrentSubmit(
                user,
                conversationId,
                key,
                "same concurrent content",
                ready,
                start
        );
    }

    private ConcurrentResult concurrentSubmit(
            Tokens user,
            String conversationId,
            String key,
            String content,
            CountDownLatch ready,
            CountDownLatch start
    ) throws Exception {
        ready.countDown();
        start.await();
        MvcResult result = mockMvc.perform(
                        post("/api/v1/conversations/{id}/messages", conversationId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .header("Idempotency-Key", key)
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "content", content,
                                        "contextVersion", 0
                                )))
                )
                .andReturn();
        return new ConcurrentResult(
                result.getResponse().getStatus(),
                result.getResponse().getContentAsString()
        );
    }

    private org.springframework.test.web.servlet.ResultActions submit(
            Tokens user,
            String conversationId,
            String key,
            long contextVersion,
            String content
    ) throws Exception {
        return mockMvc.perform(
                post("/api/v1/conversations/{id}/messages", conversationId)
                        .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                        .header("Idempotency-Key", key)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of(
                                "content", content,
                                "contextVersion", contextVersion
                        )))
        );
    }

    private JsonNode createConversation(Tokens user, String title) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/conversations")
                                .header(HttpHeaders.AUTHORIZATION, bearer(user.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of("title", title)))
                )
                .andExpect(status().isCreated())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andReturn();
        return body(result).path("data");
    }

    private Tokens createAndLoginUser(String label, String role) throws Exception {
        String suffix = UUID.randomUUID().toString().substring(0, 8);
        String username = "p4-" + label + "-" + suffix;
        String password = "P4-password-" + suffix;
        Tokens admin = login(ADMIN_USERNAME, ADMIN_PASSWORD);
        mockMvc.perform(
                        post("/api/v1/users")
                                .header(HttpHeaders.AUTHORIZATION, bearer(admin.accessToken()))
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(json(Map.of(
                                        "username", username,
                                        "password", password,
                                        "roles", new String[]{role}
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

    private int count(String sql, String value) {
        return jdbcTemplate.queryForObject(sql, Integer.class, value);
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

    private record ConcurrentResult(int status, String body) {
    }
}
