package com.livestock.platform.livestock;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.ai.AiMeasurementRequest;
import com.livestock.platform.ai.AiMeasurementResponse;
import com.livestock.platform.ai.PythonAiMeasurementClient;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
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
class P6LivestockIntegrationTest {

    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0.36")
            .withDatabaseName("livestock_app")
            .withUsername("livestock_app")
            .withPassword("p6-livestock-integration-password");

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
    PasswordEncoder passwordEncoder;

    @MockitoBean
    PythonAiMeasurementClient measurementClient;

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", REDIS::getFirstMappedPort);
        registry.add("livestock.security.jwt-secret",
                () -> "p6-livestock-jwt-secret-at-least-32-characters");
        registry.add("livestock.bootstrap-admin.enabled", () -> "false");
        registry.add("livestock.knowledge.reconciliation-enabled", () -> "false");
        registry.add("livestock.ai-service.base-url", () -> "http://127.0.0.1:1");
        registry.add("livestock.ai-service.service-token",
                () -> "p6-livestock-service-token-at-least-32-characters");
    }

    @BeforeEach
    void prepareClient() {
        reset(measurementClient);
        when(measurementClient.analyze(any())).thenAnswer(invocation -> {
            AiMeasurementRequest request = invocation.getArgument(0);
            return new AiMeasurementResponse(
                    request.requestId(),
                    request.operationId(),
                    "run_p6_livestock_001",
                    AiMeasurementResponse.Outcome.ANALYZED,
                    new AiMeasurementResponse.Analysis(
                            request.animalSnapshot().animalId(),
                            "measurement stable",
                            List.of(),
                            List.of("100 durable history rows"),
                            "continue monitoring",
                            "measurement report",
                            false
                    ),
                    "trace_p6_livestock_001"
            );
        });
    }

    @Test
    void ownerAnalysisUsesLatestHundredRowsWithoutSavingCurrentMeasurement()
            throws Exception {
        TestUser vet = createUser("VET");
        long animalId = createAnimal(vet.id(), "yak_032", "cattle");
        LocalDate start = LocalDate.of(2025, 1, 1);
        for (int index = 0; index < 105; index++) {
            insertMeasurement(
                    vet.id(),
                    animalId,
                    start.plusDays(index),
                    new BigDecimal("100.0").add(BigDecimal.valueOf(index))
            );
        }
        int before = measurementCount(animalId);

        mockMvc.perform(
                        post("/api/v1/measurements/analyze")
                                .header(HttpHeaders.AUTHORIZATION, bearer(login(vet)))
                                .header("Idempotency-Key", "measurement-owner-0001")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsBytes(Map.of(
                                        "animalId", animalId,
                                        "current", Map.of(
                                                "chestGirthCm", 211.0,
                                                "weightKg", 320.0
                                        ),
                                        "confidence", 0.92
                                )))
                )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.outcome").value("ANALYZED"))
                .andExpect(jsonPath("$.data.animalId").value(animalId))
                .andExpect(jsonPath("$.data.animalCode").value("yak_032"))
                .andExpect(jsonPath("$.data.result.usedDemoHistory").value(false));

        ArgumentCaptor<AiMeasurementRequest> captor =
                ArgumentCaptor.forClass(AiMeasurementRequest.class);
        org.mockito.Mockito.verify(measurementClient).analyze(captor.capture());
        AiMeasurementRequest sent = captor.getValue();
        assertThat(sent.animalSnapshot().animalId()).isEqualTo("yak_032");
        assertThat(sent.animalSnapshot().species()).isEqualTo("cattle");
        assertThat(sent.history()).hasSize(100);
        assertThat(sent.history().get(0).measureDate()).isEqualTo(start.plusDays(5));
        assertThat(sent.history().get(99).measureDate()).isEqualTo(start.plusDays(104));
        assertThat(sent.useDemoHistory()).isFalse();
        assertThat(sent.deadlineMs()).isEqualTo(10000);
        assertThat(sent.userId()).isEqualTo(String.valueOf(vet.id()));
        assertThat(measurementCount(animalId)).isEqualTo(before);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM audit_log WHERE actor_id = ? "
                        + "AND resource_type = 'ANIMAL' AND resource_id = ? "
                        + "AND action = 'MEASUREMENT_ANALYZED'",
                Integer.class,
                vet.id(),
                String.valueOf(animalId)
        )).isOne();
    }

    @Test
    void ownerCannotAnalyzeAnotherOwnersAnimal() throws Exception {
        TestUser caller = createUser("VET");
        TestUser owner = createUser("VET");
        long animalId = createAnimal(owner.id(), "yak_private", "cattle");

        mockMvc.perform(
                        post("/api/v1/measurements/analyze")
                                .header(HttpHeaders.AUTHORIZATION, bearer(login(caller)))
                                .header("Idempotency-Key", "measurement-owner-denied")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsBytes(Map.of(
                                        "animalId", animalId,
                                        "current", Map.of("weightKg", 300.0)
                                )))
                )
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("ANIMAL_NOT_FOUND"));
        verifyNoInteractions(measurementClient);
    }

    @Test
    void roleAndProfileGatesRunBeforeTheAiCall() throws Exception {
        TestUser ordinaryUser = createUser("USER");
        long ordinaryAnimal = createAnimal(ordinaryUser.id(), "yak_user", "cattle");
        mockMvc.perform(
                        post("/api/v1/measurements/analyze")
                                .header(HttpHeaders.AUTHORIZATION, bearer(login(ordinaryUser)))
                                .header("Idempotency-Key", "measurement-role-denied")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsBytes(Map.of(
                                        "animalId", ordinaryAnimal,
                                        "current", Map.of("weightKg", 300.0)
                                )))
                )
                .andExpect(status().isForbidden());

        TestUser vet = createUser("VET");
        long incompleteAnimal = createAnimal(vet.id(), "yak_incomplete", null);
        mockMvc.perform(
                        post("/api/v1/measurements/analyze")
                                .header(HttpHeaders.AUTHORIZATION, bearer(login(vet)))
                                .header("Idempotency-Key", "measurement-profile-denied")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsBytes(Map.of(
                                        "animalId", incompleteAnimal,
                                        "current", Map.of("weightKg", 300.0)
                                )))
                )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("ANIMAL_PROFILE_INCOMPLETE"));
        verifyNoInteractions(measurementClient);
    }

    @Test
    void databaseConstraintsPreserveOwnerAndMeasurementInvariants() {
        TestUser firstOwner = createUser("VET");
        TestUser secondOwner = createUser("VET");
        long animalId = createAnimal(firstOwner.id(), "yak_constraints", "cattle");

        assertThatThrownBy(() -> jdbcTemplate.update(
                "INSERT INTO measurement_record "
                        + "(owner_id, animal_id, measure_date, weight_kg) VALUES (?, ?, ?, ?)",
                secondOwner.id(), animalId, LocalDate.of(2026, 1, 1), new BigDecimal("250")
        )).isInstanceOf(DataAccessException.class);
        assertThatThrownBy(() -> jdbcTemplate.update(
                "INSERT INTO measurement_record (owner_id, animal_id, measure_date) "
                        + "VALUES (?, ?, ?)",
                firstOwner.id(), animalId, LocalDate.of(2026, 1, 1)
        )).isInstanceOf(DataAccessException.class);
        assertThatThrownBy(() -> jdbcTemplate.update(
                "INSERT INTO measurement_record "
                        + "(owner_id, animal_id, measure_date, weight_kg, confidence) "
                        + "VALUES (?, ?, ?, ?, ?)",
                firstOwner.id(), animalId, LocalDate.of(2026, 1, 1),
                new BigDecimal("-1"), new BigDecimal("1.2")
        )).isInstanceOf(DataAccessException.class);
    }

    private TestUser createUser(String role) {
        String suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 12);
        String username = "p6-" + role.toLowerCase() + "-" + suffix;
        String password = "P6-test-password-" + suffix;
        jdbcTemplate.update(
                "INSERT INTO sys_user "
                        + "(username, password_hash, status, security_version, version) "
                        + "VALUES (?, ?, 'ENABLED', 0, 0)",
                username,
                passwordEncoder.encode(password)
        );
        Long userId = jdbcTemplate.queryForObject(
                "SELECT id FROM sys_user WHERE username = ?",
                Long.class,
                username
        );
        jdbcTemplate.update(
                "INSERT INTO sys_user_role (user_id, role_id) "
                        + "SELECT ?, id FROM sys_role WHERE code = ?",
                userId,
                role
        );
        return new TestUser(userId, username, password);
    }

    private long createAnimal(long ownerId, String code, String species) {
        jdbcTemplate.update(
                "INSERT INTO animal (owner_id, animal_code, species, breed, sex, birth_date) "
                        + "VALUES (?, ?, ?, 'yak', 'female', '2024-01-01')",
                ownerId,
                code,
                species
        );
        return jdbcTemplate.queryForObject(
                "SELECT id FROM animal WHERE owner_id = ? AND animal_code = ?",
                Long.class,
                ownerId,
                code
        );
    }

    private void insertMeasurement(
            long ownerId,
            long animalId,
            LocalDate date,
            BigDecimal chestGirth
    ) {
        jdbcTemplate.update(
                "INSERT INTO measurement_record "
                        + "(owner_id, animal_id, measure_date, chest_girth_cm, weight_kg) "
                        + "VALUES (?, ?, ?, ?, 300)",
                ownerId,
                animalId,
                date,
                chestGirth
        );
    }

    private int measurementCount(long animalId) {
        return jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM measurement_record WHERE animal_id = ?",
                Integer.class,
                animalId
        );
    }

    private String login(TestUser user) throws Exception {
        MvcResult result = mockMvc.perform(
                        post("/api/v1/auth/login")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content(objectMapper.writeValueAsBytes(Map.of(
                                        "username", user.username(),
                                        "password", user.password()
                                )))
                )
                .andExpect(status().isOk())
                .andReturn();
        return objectMapper.readTree(result.getResponse().getContentAsByteArray())
                .at("/data/accessToken")
                .asText();
    }

    private static String bearer(String token) {
        return "Bearer " + token;
    }

    private record TestUser(long id, String username, String password) {
    }
}
