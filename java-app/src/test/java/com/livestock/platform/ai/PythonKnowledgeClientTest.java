package com.livestock.platform.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class PythonKnowledgeClientTest {

    private static final String BASE_URL = "http://python-ai.test";
    private MockRestServiceServer server;
    private PythonKnowledgeClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder().baseUrl(BASE_URL);
        server = MockRestServiceServer.bindTo(builder).build();
        AiServiceProperties properties = new AiServiceProperties();
        properties.setBaseUrl(BASE_URL);
        properties.setServiceToken("test-service-token-at-least-32-characters");
        properties.setReadTimeout(Duration.ofSeconds(1));
        client = new PythonKnowledgeClient(
                builder.build(),
                properties,
                new ObjectMapper().findAndRegisterModules(),
                new AiCallMetrics(
                        new io.micrometer.core.instrument.simple.SimpleMeterRegistry()
                )
        );
    }

    @Test
    void submitsWithStableHeadersAndValidatesAcceptedContract() {
        KnowledgeIngestionRequest request = request();
        server.expect(once(), requestTo(BASE_URL + "/internal/v1/ai/knowledge/ingestions"))
                .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer test-service-token-at-least-32-characters"))
                .andExpect(header(RequestIds.HEADER_NAME, request.requestId()))
                .andExpect(header("Idempotency-Key", request.operationId()))
                .andRespond(httpRequest -> {
                    org.springframework.mock.http.client.MockClientHttpResponse response =
                            new org.springframework.mock.http.client.MockClientHttpResponse(
                                    ("{\"requestId\":\"" + request().requestId()
                                            + "\",\"operationId\":\"" + request().operationId()
                                            + "\",\"runId\":\"run_12345678\","
                                            + "\"type\":\"DOCUMENT_INDEX\",\"status\":\"ACCEPTED\","
                                            + "\"submittedAt\":\"2026-08-04T00:00:00Z\"}")
                                            .getBytes(java.nio.charset.StandardCharsets.UTF_8),
                                    org.springframework.http.HttpStatus.ACCEPTED
                            );
                    response.getHeaders().set(RequestIds.HEADER_NAME, request().requestId());
                    response.getHeaders().set(
                            HttpHeaders.LOCATION,
                            "/internal/v1/ai/operations/" + request().operationId()
                    );
                    response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
                    return response;
                });

        KnowledgeIngestionAccepted accepted = client.submit(request);

        assertThat(accepted.status()).isEqualTo(DocumentIndexOperation.Status.ACCEPTED);
        assertThat(accepted.runId()).isEqualTo("run_12345678");
        server.verify();
    }

    @Test
    void malformedSuccessfulSubmissionIsClassifiedAsUnknown() {
        server.expect(requestTo(BASE_URL + "/internal/v1/ai/knowledge/ingestions"))
                .andRespond(withSuccess("{\"malformed\":true}", MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.submit(request()))
                .isInstanceOf(KnowledgeClientException.class)
                .satisfies(error -> assertThat(
                        ((KnowledgeClientException) error).submissionUnknown()
                ).isTrue());
    }

    private static KnowledgeIngestionRequest request() {
        return new KnowledgeIngestionRequest(
                "req_knowledge_0001",
                "op_knowledge_0001",
                "1",
                "doc_12345678-1234-1234-1234-123456789012",
                "test",
                "users/1/documents/guide.txt",
                "guide.txt",
                "text/plain",
                12,
                "a".repeat(64),
                false
        );
    }
}
