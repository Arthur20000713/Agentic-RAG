package com.livestock.platform.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

class PythonAiChatClientTest {

    private static final String REQUEST_ID = "req_p5_client_0001";
    private static final String OPERATION_ID = "operation_p5_client_0001";

    private final ObjectMapper objectMapper = new ObjectMapper().findAndRegisterModules();
    private final AtomicReference<ExchangeHandler> handler = new AtomicReference<>();
    private final AtomicReference<ExchangeHandler> runHandler = new AtomicReference<>();
    private final AtomicInteger calls = new AtomicInteger();
    private final AtomicInteger runCalls = new AtomicInteger();
    private HttpServer server;
    private ExecutorService executor;
    private AiServiceProperties properties;
    private CircuitBreaker circuitBreaker;
    private Bulkhead bulkhead;

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        executor = Executors.newCachedThreadPool();
        server.setExecutor(executor);
        server.createContext("/internal/v1/ai/chat", exchange -> {
            calls.incrementAndGet();
            handler.get().handle(exchange);
        });
        server.createContext("/internal/v1/ai/runs/", exchange -> {
            runCalls.incrementAndGet();
            runHandler.get().handle(exchange);
        });
        server.start();
        properties = new AiServiceProperties();
        properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
        properties.setServiceToken("p5-client-service-token-32-characters");
        circuitBreaker = CircuitBreaker.of(
                "p5-test",
                CircuitBreakerConfig.custom()
                        .slidingWindowSize(2)
                        .minimumNumberOfCalls(2)
                        .failureRateThreshold(50)
                        .waitDurationInOpenState(Duration.ofSeconds(30))
                        .recordException(exception ->
                                exception instanceof AiChatClientException failure
                                        && failure.circuitFailure()
                        )
                        .build()
        );
        bulkhead = Bulkhead.of(
                "p5-test",
                BulkheadConfig.custom()
                        .maxConcurrentCalls(1)
                        .maxWaitDuration(Duration.ZERO)
                        .build()
        );
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
        executor.shutdownNow();
    }

    @Test
    void sendsContractHeadersAndParsesSupportedAnswer() {
        handler.set(exchange -> {
            assertThat(exchange.getRequestHeaders().getFirst(HttpHeaders.AUTHORIZATION))
                    .isEqualTo("Bearer " + properties.serviceToken());
            assertThat(exchange.getRequestHeaders().getFirst("X-Request-ID"))
                    .isEqualTo(REQUEST_ID);
            assertThat(exchange.getRequestHeaders().getFirst("Idempotency-Key"))
                    .isEqualTo(OPERATION_ID);
            JsonNode requestBody = objectMapper.readTree(exchange.getRequestBody());
            assertThat(requestBody.path("query").asText()).isEqualTo("How is the cow?");
            assertThat(requestBody.path("contextVersion").asLong()).isEqualTo(3);
            respond(exchange, 200, validResponse("SUPPORTED", "ANSWERED", "[]"));
        });

        AiChatResponse response = client(Duration.ofSeconds(2)).chat(request());

        assertThat(response.outcome()).isEqualTo(AiChatResponse.Outcome.ANSWERED);
        assertThat(response.contextVersion()).isEqualTo(4);
        assertThat(calls).hasValue(1);
    }

    @Test
    void serviceUnavailableIsMappedAndChatIsNotRetried() {
        handler.set(exchange -> respond(
                exchange,
                503,
                """
                {
                  "requestId":"req_p5_client_0001",
                  "operationId":"operation_p5_client_0001",
                  "error":{
                    "code":"AI_SERVICE_UNAVAILABLE",
                    "message":"temporarily unavailable",
                    "retryable":true,
                    "details":{}
                  }
                }
                """
        ));

        assertThatThrownBy(() -> client(Duration.ofSeconds(2)).chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                    assertThat(failure.code()).isEqualTo("AI_SERVICE_UNAVAILABLE");
                    assertThat(failure.remoteCode()).isEqualTo("AI_SERVICE_UNAVAILABLE");
                    assertThat(failure.retryable()).isTrue();
                    assertThat(failure.submissionUnknown()).isFalse();
                });
        assertThat(calls).hasValue(1);
    }

    @Test
    void executionStoreFailureMarksSubmissionUnknownWithoutRetry() {
        handler.set(exchange -> respond(
                exchange,
                503,
                """
                {
                  "requestId":"req_p5_client_0001",
                  "operationId":"operation_p5_client_0001",
                  "error":{
                    "code":"EXECUTION_STORE_UNAVAILABLE",
                    "message":"execution result could not be persisted",
                    "retryable":true,
                    "details":{}
                  }
                }
                """
        ));

        assertThatThrownBy(() -> client(Duration.ofSeconds(2)).chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                    assertThat(failure.code()).isEqualTo("AI_SERVICE_UNAVAILABLE");
                    assertThat(failure.remoteCode())
                            .isEqualTo("EXECUTION_STORE_UNAVAILABLE");
                    assertThat(failure.submissionUnknown()).isTrue();
                    assertThat(failure.circuitFailure()).isTrue();
                });
        assertThat(calls).hasValue(1);
    }

    @Test
    void successfulNullBodyIsMappedToProtocolError() {
        handler.set(exchange -> respond(exchange, 200, "null"));

        assertThatThrownBy(() -> client(Duration.ofSeconds(2)).chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                    assertThat(failure.code()).isEqualTo("AI_PROTOCOL_ERROR");
                    assertThat(failure.submissionUnknown()).isTrue();
                    assertThat(failure.circuitFailure()).isTrue();
                });
        assertThat(calls).hasValue(1);
    }

    @Test
    void malformedServerErrorIsUnknownAndCountsTowardCircuit() {
        handler.set(exchange -> respond(exchange, 503, "<html>bad gateway</html>"));

        assertThatThrownBy(() -> client(Duration.ofSeconds(2)).chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                    assertThat(failure.code()).isEqualTo("AI_PROTOCOL_ERROR");
                    assertThat(failure.submissionUnknown()).isTrue();
                    assertThat(failure.circuitFailure()).isTrue();
                });
        assertThat(calls).hasValue(1);
    }

    @Test
    void mismatchedErrorCorrelationIsRejected() {
        handler.set(exchange -> respond(
                exchange,
                503,
                """
                {
                  "requestId":"req_wrong_correlation",
                  "operationId":"operation_p5_client_0001",
                  "error":{
                    "code":"AI_SERVICE_UNAVAILABLE",
                    "message":"temporarily unavailable",
                    "retryable":true,
                    "details":{}
                  }
                }
                """
        ));

        assertThatThrownBy(() -> client(Duration.ofSeconds(2)).chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                    assertThat(failure.code()).isEqualTo("AI_PROTOCOL_ERROR");
                    assertThat(failure.submissionUnknown()).isTrue();
                });
        assertThat(calls).hasValue(1);
    }

    @Test
    void explicitDeadlineFailureIsKnownAndNotRetried() {
        handler.set(exchange -> respond(
                exchange,
                504,
                """
                {
                  "requestId":"req_p5_client_0001",
                  "operationId":"operation_p5_client_0001",
                  "error":{
                    "code":"DEADLINE_EXCEEDED",
                    "message":"chat deadline exceeded",
                    "retryable":false,
                    "details":{}
                  }
                }
                """
        ));

        assertThatThrownBy(() -> client(Duration.ofSeconds(2)).chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                    assertThat(failure.code()).isEqualTo("AI_TIMEOUT");
                    assertThat(failure.remoteCode()).isEqualTo("DEADLINE_EXCEEDED");
                    assertThat(failure.submissionUnknown()).isFalse();
                    assertThat(failure.circuitFailure()).isTrue();
                });
        assertThat(calls).hasValue(1);
    }

    @Test
    void concurrencyLimitedResponsesDoNotOpenCircuit() {
        handler.set(exchange -> respond(
                exchange,
                429,
                """
                {
                  "requestId":"req_p5_client_0001",
                  "operationId":"operation_p5_client_0001",
                  "error":{
                    "code":"CONCURRENCY_LIMITED",
                    "message":"operation is already running",
                    "retryable":true,
                    "details":{}
                  }
                }
                """
        ));
        PythonAiChatClient client = client(Duration.ofSeconds(2));

        for (int index = 0; index < 3; index++) {
            assertThatThrownBy(() -> client.chat(request()))
                    .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                        assertThat(failure.code()).isEqualTo("AI_BUSY");
                        assertThat(failure.circuitFailure()).isFalse();
                    });
        }
        assertThat(circuitBreaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        assertThat(calls).hasValue(3);
    }

    @Test
    void lowConfidenceResponseCannotContainFabricatedSources() {
        String fabricatedSource = """
                [{
                  "collection":"default",
                  "documentId":"doc-1",
                  "title":"Fabricated",
                  "sourceUri":null,
                  "page":1,
                  "sectionTitle":null,
                  "chunkId":"chunk-1",
                  "score":0.9
                }]
                """;
        handler.set(exchange -> respond(
                exchange,
                200,
                validResponse("LOW_CONFIDENCE", "LOW_CONFIDENCE", fabricatedSource)
        ));

        assertThatThrownBy(() -> client(Duration.ofSeconds(2)).chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                    assertThat(failure.code()).isEqualTo("AI_PROTOCOL_ERROR");
                    assertThat(failure.submissionUnknown()).isTrue();
                    assertThat(failure.circuitFailure()).isTrue();
                });
    }

    @Test
    void readTimeoutMarksSubmissionUnknownWithoutRetry() {
        handler.set(exchange -> {
            try {
                Thread.sleep(400);
                respond(exchange, 200, validResponse("SUPPORTED", "ANSWERED", "[]"));
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
        });

        assertThatThrownBy(() -> client(Duration.ofMillis(100)).chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                    assertThat(failure.code()).isEqualTo("AI_SUBMISSION_UNKNOWN");
                    assertThat(failure.submissionUnknown()).isTrue();
                    assertThat(failure.circuitFailure()).isTrue();
                });
        assertThat(calls).hasValue(1);
    }

    @Test
    void fullBulkheadRejectsBeforeCallingPython() {
        handler.set(exchange -> respond(
                exchange,
                200,
                validResponse("SUPPORTED", "ANSWERED", "[]")
        ));
        assertThat(bulkhead.tryAcquirePermission()).isTrue();
        try {
            assertThatThrownBy(() -> client(Duration.ofSeconds(2)).chat(request()))
                    .isInstanceOfSatisfying(AiChatClientException.class, failure -> {
                        assertThat(failure.code()).isEqualTo("AI_BUSY");
                        assertThat(failure.circuitFailure()).isFalse();
                    });
        } finally {
            bulkhead.onComplete();
        }
        assertThat(calls).hasValue(0);
    }

    @Test
    void repeatedRetryableFailuresOpenCircuit() {
        handler.set(exchange -> respond(
                exchange,
                503,
                """
                {
                  "requestId":"req_p5_client_0001",
                  "operationId":"operation_p5_client_0001",
                  "error":{
                    "code":"MODEL_UNAVAILABLE",
                    "message":"model unavailable",
                    "retryable":true,
                    "details":{}
                  }
                }
                """
        ));
        PythonAiChatClient client = client(Duration.ofSeconds(2));

        for (int index = 0; index < 2; index++) {
            assertThatThrownBy(() -> client.chat(request()))
                    .isInstanceOf(AiChatClientException.class);
        }
        assertThat(circuitBreaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);
        assertThatThrownBy(() -> client.chat(request()))
                .isInstanceOfSatisfying(AiChatClientException.class, failure ->
                        assertThat(failure.getMessage())
                                .isEqualTo("AI circuit breaker is open")
                );
        assertThat(calls).hasValue(2);
    }

    @Test
    void reconcilesSucceededRunAndTreatsOperationNotFoundAsEmpty() {
        runHandler.set(exchange -> {
            assertThat(exchange.getRequestHeaders().getFirst(HttpHeaders.AUTHORIZATION))
                    .isEqualTo("Bearer " + properties.serviceToken());
            assertThat(exchange.getRequestHeaders().getFirst("X-Request-ID"))
                    .isEqualTo("req_p5_reconcile_0001");
            assertThat(exchange.getRequestHeaders().getFirst("Idempotency-Key"))
                    .isNull();
            respond(
                    exchange,
                    200,
                    """
                    {
                      "requestId":"req_p5_reconcile_0001",
                      "operationId":"operation_p5_client_0001",
                      "runId":"run_p5_client_0001",
                      "type":"AI_CHAT",
                      "status":"SUCCEEDED",
                      "result":%s,
                      "error":null,
                      "createdAt":"2026-07-30T00:00:00Z",
                      "updatedAt":"2026-07-30T00:00:01Z",
                      "expiresAt":"2026-07-30T01:00:00Z"
                    }
                    """.formatted(validResponse("SUPPORTED", "ANSWERED", "[]")),
                    "req_p5_reconcile_0001"
            );
        });
        PythonAiChatClient client = client(Duration.ofSeconds(2));

        AiChatRun run = client.findRun(
                "req_p5_reconcile_0001",
                OPERATION_ID
        ).orElseThrow();
        assertThat(run.status()).isEqualTo(AiChatRun.Status.SUCCEEDED);
        assertThat(run.result().answer()).isEqualTo("Conservative answer");

        runHandler.set(exchange -> respond(
                exchange,
                404,
                """
                {
                  "requestId":"req_p5_reconcile_0002",
                  "operationId":"operation_p5_client_0001",
                  "error":{
                    "code":"OPERATION_NOT_FOUND",
                    "message":"operation not found",
                    "retryable":false,
                    "details":{}
                  }
                }
                """,
                "req_p5_reconcile_0002"
        ));
        assertThat(client.findRun(
                "req_p5_reconcile_0002",
                OPERATION_ID
        )).isEmpty();
        assertThat(runCalls).hasValue(2);
    }

    @Test
    void rejectsSucceededRunWithMismatchedNestedRunId() {
        runHandler.set(exchange -> respond(
                exchange,
                200,
                """
                {
                  "requestId":"req_p5_reconcile_0001",
                  "operationId":"operation_p5_client_0001",
                  "runId":"run_p5_client_0002",
                  "type":"AI_CHAT",
                  "status":"SUCCEEDED",
                  "result":%s,
                  "error":null,
                  "createdAt":"2026-07-30T00:00:00Z",
                  "updatedAt":"2026-07-30T00:00:01Z",
                  "expiresAt":"2026-07-30T01:00:00Z"
                }
                """.formatted(validResponse("SUPPORTED", "ANSWERED", "[]")),
                "req_p5_reconcile_0001"
        ));

        assertThatThrownBy(() -> client(Duration.ofSeconds(2)).findRun(
                "req_p5_reconcile_0001",
                OPERATION_ID
        )).isInstanceOfSatisfying(AiChatClientException.class, failure ->
                assertThat(failure.code()).isEqualTo("AI_PROTOCOL_ERROR")
        );
    }

    private PythonAiChatClient client(Duration readTimeout) {
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(1))
                .build();
        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(readTimeout);
        RestClient restClient = RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(factory)
                .build();
        return new PythonAiChatClient(
                restClient,
                properties,
                objectMapper,
                circuitBreaker,
                bulkhead,
                new AiCallMetrics(
                        new io.micrometer.core.instrument.simple.SimpleMeterRegistry()
                )
        );
    }

    private AiChatRequest request() {
        return new AiChatRequest(
                REQUEST_ID,
                OPERATION_ID,
                "conversation-42",
                "user-7",
                "How is the cow?",
                null,
                List.of(),
                objectMapper.createObjectNode()
                        .put("schemaVersion", 1)
                        .set("slots", objectMapper.createObjectNode()),
                3,
                60000
        );
    }

    private String validResponse(
            String evidenceStatus,
            String outcome,
            String sources
    ) {
        return """
                {
                  "requestId":"req_p5_client_0001",
                  "operationId":"operation_p5_client_0001",
                  "runId":"run_p5_client_0001",
                  "outcome":"%s",
                  "answer":"Conservative answer",
                  "intent":"disease_consultation",
                  "riskLevel":"HIGH",
                  "evidenceStatus":"%s",
                  "sources":%s,
                  "followUpQuestions":[],
                  "toolsUsed":["query_knowledge_hub"],
                  "safety":{"decision":"ALLOWED","reasonCode":null},
                  "nextContext":{"schemaVersion":1,"slots":{}},
                  "contextVersion":4,
                  "traceId":"trace_p5_client_0001"
                }
                """.formatted(outcome, evidenceStatus, sources);
    }

    private static void respond(
            HttpExchange exchange,
            int status,
            String body
    ) throws IOException {
        respond(exchange, status, body, REQUEST_ID);
    }

    private static void respond(
            HttpExchange exchange,
            int status,
            String body,
            String requestId
    ) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.getResponseHeaders().set("X-Request-ID", requestId);
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
        exchange.close();
    }

    @FunctionalInterface
    private interface ExchangeHandler {
        void handle(HttpExchange exchange) throws IOException;
    }
}
