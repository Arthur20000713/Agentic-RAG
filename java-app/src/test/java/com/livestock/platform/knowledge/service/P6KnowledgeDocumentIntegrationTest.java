package com.livestock.platform.knowledge.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.ai.DocumentIndexOperation;
import com.livestock.platform.ai.DocumentIndexResult;
import com.livestock.platform.ai.KnowledgeClientException;
import com.livestock.platform.ai.KnowledgeIngestionAccepted;
import com.livestock.platform.ai.KnowledgeIngestionRequest;
import com.livestock.platform.ai.PythonKnowledgeClient;
import com.livestock.platform.common.web.RequestIds;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
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
class P6KnowledgeDocumentIntegrationTest {

    private static final String ADMIN_USERNAME = "p6-knowledge-admin";
    private static final String ADMIN_PASSWORD = "P6-knowledge-admin-password-2026";
    private static final Path UPLOAD_ROOT = Path.of(
            System.getProperty("java.io.tmpdir"),
            "livestock-p6-knowledge-" + UUID.randomUUID()
    );

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("livestock_app")
            .withUsername("livestock_app")
            .withPassword("p6-integration-password");

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
    DocumentIndexReconciler reconciler;

    @MockitoBean
    PythonKnowledgeClient knowledgeClient;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", REDIS::getFirstMappedPort);
        registry.add("livestock.security.jwt-secret", () -> "p6-jwt-secret-at-least-32-characters");
        registry.add("livestock.bootstrap-admin.enabled", () -> "true");
        registry.add("livestock.bootstrap-admin.username", () -> ADMIN_USERNAME);
        registry.add("livestock.bootstrap-admin.password", () -> ADMIN_PASSWORD);
        registry.add("livestock.knowledge.shared-root", UPLOAD_ROOT::toString);
        registry.add("livestock.knowledge.reconciliation-enabled", () -> "false");
        registry.add("livestock.ai-service.base-url", () -> "http://127.0.0.1:1");
        registry.add(
                "livestock.ai-service.service-token",
                () -> "p6-integration-service-token-at-least-32-characters"
        );
    }

    @BeforeEach
    void prepare() throws Exception {
        Files.createDirectories(UPLOAD_ROOT);
        reset(knowledgeClient);
        when(knowledgeClient.submit(any())).thenAnswer(invocation -> {
            KnowledgeIngestionRequest request = invocation.getArgument(0);
            return accepted(request);
        });
        when(knowledgeClient.findOperation(anyString(), anyString())).thenAnswer(invocation ->
                Optional.of(succeeded(
                        invocation.getArgument(0),
                        invocation.getArgument(1)
                ))
        );
    }

    @Test
    void uploadReplayAndResponseLossReconciliationProduceOneBusinessResult()
            throws Exception {
        String accessToken = login();
        String idempotencyKey = "p6-upload-" + UUID.randomUUID();
        JsonNode created = upload(accessToken, idempotencyKey, "feeding.txt", "feeding guidance");
        long taskId = created.at("/data/task/id").asLong();
        String documentId = created.at("/data/document/id").asText();

        JsonNode replay = upload(accessToken, idempotencyKey, "feeding.txt", "feeding guidance");
        assertThat(replay.at("/data/idempotentReplay").asBoolean()).isTrue();
        assertThat(replay.at("/data/task/id").asLong()).isEqualTo(taskId);
        assertThat(count(
                "SELECT COUNT(*) FROM knowledge_document WHERE client_idempotency_key = ?",
                idempotencyKey
        )).isOne();
        assertThat(count(
                "SELECT COUNT(*) FROM biz_task WHERE id = ? AND type = 'DOCUMENT_INDEX'",
                taskId
        ))
                .isOne();

        doThrow(new KnowledgeClientException(
                "DOCUMENT_SUBMISSION_UNKNOWN",
                "response lost",
                true,
                true,
                null
        )).when(knowledgeClient).submit(any());
        reconciler.reconcileOne(taskId);
        assertThat(taskStatus(taskId)).isEqualTo("SUBMIT_UNKNOWN");

        reconciler.reconcileOne(taskId);
        assertThat(taskStatus(taskId)).isEqualTo("SUCCEEDED");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT status FROM knowledge_document WHERE document_id = ?",
                String.class,
                documentId
        )).isEqualTo("VALIDATED");
        verify(knowledgeClient).submit(any());
        verify(knowledgeClient).findOperation(anyString(), anyString());

        mockMvc.perform(
                        get("/api/v1/documents/{id}", documentId)
                                .header(HttpHeaders.AUTHORIZATION, bearer(accessToken))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("VALIDATED"))
                .andExpect(jsonPath("$.data.executionMode").value("FAKE"))
                .andExpect(jsonPath("$.data.taskId").value(String.valueOf(taskId)));

        assertThat(count(
                "SELECT COUNT(*) FROM audit_log WHERE resource_id = ? AND action = 'DOCUMENT_UPLOADED'",
                documentId
        )).isOne();
        assertThat(count(
                "SELECT COUNT(*) FROM audit_log WHERE resource_id = ? AND action = 'DOCUMENT_INDEX_COMPLETED'",
                documentId
        )).isOne();
        String objectKey = jdbcTemplate.queryForObject(
                "SELECT object_key FROM knowledge_document WHERE document_id = ?",
                String.class,
                documentId
        );
        assertThat(objectKey).startsWith("users/").doesNotContain(UPLOAD_ROOT.toString());
    }

    @Test
    void sameIdempotencyKeyWithDifferentContentIsRejected() throws Exception {
        String accessToken = login();
        String idempotencyKey = "p6-conflict-" + UUID.randomUUID();
        upload(accessToken, idempotencyKey, "guide.txt", "first content");

        MockMultipartFile changed = new MockMultipartFile(
                "file",
                "guide.txt",
                "text/plain",
                "different content".getBytes(StandardCharsets.UTF_8)
        );
        mockMvc.perform(
                        multipart("/api/v1/documents")
                                .file(changed)
                                .header(HttpHeaders.AUTHORIZATION, bearer(accessToken))
                                .header("Idempotency-Key", idempotencyKey)
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("IDEMPOTENCY_CONFLICT"));
        assertThat(count(
                "SELECT COUNT(*) FROM knowledge_document WHERE client_idempotency_key = ?",
                idempotencyKey
        )).isOne();
    }

    private JsonNode upload(
            String accessToken,
            String idempotencyKey,
            String fileName,
            String content
    ) throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                fileName,
                "text/plain",
                content.getBytes(StandardCharsets.UTF_8)
        );
        MvcResult result = mockMvc.perform(
                        multipart("/api/v1/documents")
                                .file(file)
                                .header(HttpHeaders.AUTHORIZATION, bearer(accessToken))
                                .header("Idempotency-Key", idempotencyKey)
                                .header(RequestIds.HEADER_NAME, "req-p6-" + UUID.randomUUID())
                )
                .andExpect(status().isAccepted())
                .andExpect(header().exists(HttpHeaders.LOCATION))
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsByteArray());
    }

    private String login() throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/auth/login")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsBytes(java.util.Map.of(
                                        "username", ADMIN_USERNAME,
                                        "password", ADMIN_PASSWORD
                                )))
                )
                .andExpect(status().isOk())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsByteArray())
                .at("/data/accessToken")
                .asText();
    }

    private String taskStatus(long taskId) {
        return jdbcTemplate.queryForObject(
                "SELECT status FROM biz_task WHERE id = ?",
                String.class,
                taskId
        );
    }

    private int count(String sql, Object... arguments) {
        return jdbcTemplate.queryForObject(sql, Integer.class, arguments);
    }

    private static KnowledgeIngestionAccepted accepted(KnowledgeIngestionRequest request) {
        return new KnowledgeIngestionAccepted(
                request.requestId(),
                request.operationId(),
                "run_" + request.operationId(),
                "DOCUMENT_INDEX",
                DocumentIndexOperation.Status.RUNNING,
                Instant.now()
        );
    }

    private DocumentIndexOperation succeeded(String requestId, String operationId) {
        String documentId = jdbcTemplate.queryForObject(
                "SELECT document_id FROM knowledge_document WHERE operation_id = ?",
                String.class,
                operationId
        );
        String sha256 = jdbcTemplate.queryForObject(
                "SELECT sha256 FROM knowledge_document WHERE operation_id = ?",
                String.class,
                operationId
        );
        Instant now = Instant.now();
        return new DocumentIndexOperation(
                requestId,
                operationId,
                "run_" + operationId,
                "DOCUMENT_INDEX",
                DocumentIndexOperation.Status.SUCCEEDED,
                100,
                new DocumentIndexResult(
                        documentId,
                        sha256,
                        "test",
                        false,
                        false,
                        0,
                        DocumentIndexResult.ExecutionMode.FAKE
                ),
                null,
                now.minusSeconds(1),
                now.minusSeconds(1),
                now,
                now,
                now.plusSeconds(3600)
        );
    }

    private static String bearer(String token) {
        return "Bearer " + token;
    }
}
