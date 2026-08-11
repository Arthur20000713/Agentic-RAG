package com.livestock.platform.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.http.client.MockClientHttpResponse;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class PythonAiMeasurementClientTest {

    private static final String BASE_URL = "http://python-ai.test";
    private MockRestServiceServer server;
    private PythonAiMeasurementClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder().baseUrl(BASE_URL);
        server = MockRestServiceServer.bindTo(builder).build();
        AiServiceProperties properties = new AiServiceProperties();
        properties.setBaseUrl(BASE_URL);
        properties.setServiceToken("test-service-token-at-least-32-characters");
        client = new PythonAiMeasurementClient(
                builder.build(),
                properties,
                new ObjectMapper().findAndRegisterModules(),
                new AiCallMetrics(
                        new io.micrometer.core.instrument.simple.SimpleMeterRegistry()
                )
        );
    }

    @Test
    void sendsOneStablePostAndValidatesTheResponseContract() {
        AiMeasurementRequest request = request();
        server.expect(
                        once(),
                        requestTo(BASE_URL + "/internal/v1/ai/measurements/analyze")
                )
                .andExpect(header(HttpHeaders.AUTHORIZATION,
                        "Bearer test-service-token-at-least-32-characters"))
                .andExpect(header(RequestIds.HEADER_NAME, request.requestId()))
                .andExpect(header("Idempotency-Key", request.operationId()))
                .andExpect(jsonPath("$.animalSnapshot.birthDate").value("2025-01-01"))
                .andExpect(jsonPath("$.history[0].measureDate").value("2026-07-01"))
                .andRespond(ignored -> response(
                        HttpStatus.OK,
                        request.requestId(),
                        "{\"requestId\":\"" + request.requestId()
                                + "\",\"operationId\":\"" + request.operationId()
                                + "\",\"runId\":\"run_measure_001\","
                                + "\"outcome\":\"ANALYZED\",\"result\":{"
                                + "\"animalId\":\"yak_032\",\"summary\":\"stable\","
                                + "\"abnormalItems\":[],\"evidence\":[\"history\"],"
                                + "\"recommendation\":\"continue monitoring\","
                                + "\"report\":\"stable report\",\"usedDemoHistory\":false},"
                                + "\"traceId\":\"trace_measure_001\"}"
                ));

        AiMeasurementResponse result = client.analyze(request);

        assertThat(result.outcome()).isEqualTo(AiMeasurementResponse.Outcome.ANALYZED);
        assertThat(result.result().animalId()).isEqualTo("yak_032");
        server.verify();
    }

    @Test
    void rejectsAContractBreakingSuccessfulResponse() {
        AiMeasurementRequest request = request();
        server.expect(once(), requestTo(BASE_URL + "/internal/v1/ai/measurements/analyze"))
                .andRespond(ignored -> response(
                        HttpStatus.OK,
                        request.requestId(),
                        "{\"requestId\":\"" + request.requestId()
                                + "\",\"operationId\":\"" + request.operationId()
                                + "\",\"runId\":\"run_measure_001\","
                                + "\"outcome\":\"ANALYZED\",\"result\":{"
                                + "\"animalId\":\"another-animal\",\"summary\":\"stable\","
                                + "\"abnormalItems\":[],\"evidence\":[],"
                                + "\"recommendation\":\"monitor\",\"report\":\"report\","
                                + "\"usedDemoHistory\":false},\"traceId\":\"trace_001\"}"
                ));

        assertThatThrownBy(() -> client.analyze(request))
                .isInstanceOf(MeasurementClientException.class)
                .satisfies(error -> {
                    MeasurementClientException failure = (MeasurementClientException) error;
                    assertThat(failure.status()).isEqualTo(HttpStatus.BAD_GATEWAY);
                    assertThat(failure.code()).isEqualTo("AI_PROTOCOL_ERROR");
                });
        server.verify();
    }

    @Test
    void mapsStructuredServiceUnavailableWithoutRetrying() {
        AiMeasurementRequest request = request();
        server.expect(once(), requestTo(BASE_URL + "/internal/v1/ai/measurements/analyze"))
                .andRespond(ignored -> response(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        request.requestId(),
                        "{\"requestId\":\"" + request.requestId()
                                + "\",\"operationId\":null,\"error\":{"
                                + "\"code\":\"MODEL_UNAVAILABLE\","
                                + "\"message\":\"unavailable\",\"retryable\":true,"
                                + "\"details\":{}}}"
                ));

        assertThatThrownBy(() -> client.analyze(request))
                .isInstanceOf(MeasurementClientException.class)
                .satisfies(error -> {
                    MeasurementClientException failure = (MeasurementClientException) error;
                    assertThat(failure.status()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
                    assertThat(failure.code()).isEqualTo("AI_SERVICE_UNAVAILABLE");
                    assertThat(failure.retryable()).isTrue();
                });
        server.verify();
    }

    private static MockClientHttpResponse response(
            HttpStatus status,
            String requestId,
            String body
    ) {
        MockClientHttpResponse response = new MockClientHttpResponse(
                body.getBytes(StandardCharsets.UTF_8),
                status
        );
        response.getHeaders().set(RequestIds.HEADER_NAME, requestId);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        return response;
    }

    private static AiMeasurementRequest request() {
        return new AiMeasurementRequest(
                "req_measure_0001",
                "op_measure_0001",
                "7",
                new AiMeasurementRequest.AnimalSnapshot(
                        "yak_032",
                        "cattle",
                        "yak",
                        "female",
                        LocalDate.of(2025, 1, 1),
                        Map.of("databaseId", 11L)
                ),
                18,
                new AiMeasurementRequest.Values(
                        null,
                        null,
                        new BigDecimal("121.0"),
                        null,
                        null,
                        new BigDecimal("210.0")
                ),
                List.of(new AiMeasurementRequest.HistoryItem(
                        LocalDate.of(2026, 7, 1),
                        null,
                        null,
                        new BigDecimal("120.0"),
                        null,
                        null,
                        new BigDecimal("205.0")
                )),
                new BigDecimal("0.92"),
                false,
                10000
        );
    }
}
