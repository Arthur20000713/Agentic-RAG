package com.livestock.platform.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import java.io.IOException;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
public class PythonAiMeasurementClient {

    private final RestClient restClient;
    private final AiServiceProperties properties;
    private final ObjectMapper objectMapper;
    private final AiCallMetrics metrics;

    public PythonAiMeasurementClient(
            @Qualifier("aiMeasurementRestClient") RestClient restClient,
            AiServiceProperties properties,
            ObjectMapper objectMapper,
            AiCallMetrics metrics
    ) {
        this.restClient = restClient;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.metrics = metrics;
    }

    public AiMeasurementResponse analyze(AiMeasurementRequest request) {
        return metrics.record(
                AiCallMetrics.Operation.MEASUREMENT,
                () -> analyzeWithoutMetrics(request),
                result -> result.outcome().name()
        );
    }

    private AiMeasurementResponse analyzeWithoutMetrics(AiMeasurementRequest request) {
        try {
            return restClient.post()
                    .uri("/internal/v1/ai/measurements/analyze")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + properties.serviceToken())
                    .header(RequestIds.HEADER_NAME, request.requestId())
                    .header("Idempotency-Key", request.operationId())
                    .body(request)
                    .exchange((httpRequest, response) -> {
                        if (!response.getStatusCode().is2xxSuccessful()) {
                            throw remoteFailure(request, response);
                        }
                        AiMeasurementResponse result;
                        try {
                            result = objectMapper.readValue(
                                    response.getBody(),
                                    AiMeasurementResponse.class
                            );
                        } catch (IOException | IllegalArgumentException exception) {
                            throw protocolFailure(exception);
                        }
                        validateSuccess(request, response, result);
                        return result;
                    });
        } catch (MeasurementClientException exception) {
            throw exception;
        } catch (ResourceAccessException exception) {
            throw failure(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "AI_TIMEOUT",
                    "Measurement analysis timed out",
                    true,
                    exception
            );
        } catch (RestClientException exception) {
            throw failure(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "AI_SERVICE_UNAVAILABLE",
                    "Measurement analysis service is unavailable",
                    true,
                    exception
            );
        }
    }

    private MeasurementClientException remoteFailure(
            AiMeasurementRequest request,
            org.springframework.http.client.ClientHttpResponse response
    ) {
        AiServiceErrorResponse payload;
        HttpStatus status;
        try {
            status = HttpStatus.resolve(response.getStatusCode().value());
            payload = objectMapper.readValue(response.getBody(), AiServiceErrorResponse.class);
        } catch (IOException | IllegalArgumentException exception) {
            return protocolFailure(exception);
        }
        if (payload == null || payload.error() == null
                || payload.error().code() == null || payload.error().code().isBlank()
                || payload.error().message() == null || payload.error().message().isBlank()
                || !request.requestId().equals(
                response.getHeaders().getFirst(RequestIds.HEADER_NAME)
        ) || !request.requestId().equals(payload.requestId())
                || (payload.operationId() != null
                && !request.operationId().equals(payload.operationId()))) {
            return protocolFailure(null);
        }
        if (status == null) {
            return protocolFailure(null);
        }
        return switch (status) {
            case BAD_REQUEST, UNPROCESSABLE_ENTITY -> failure(
                    HttpStatus.BAD_REQUEST,
                    "MEASUREMENT_REQUEST_REJECTED",
                    "AI service rejected the measurement request",
                    false,
                    null
            );
            case UNAUTHORIZED, FORBIDDEN -> failure(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "AI_SERVICE_AUTH_FAILED",
                    "AI service authentication failed",
                    false,
                    null
            );
            case CONFLICT -> failure(
                    HttpStatus.CONFLICT,
                    "AI_CONFLICT",
                    "Measurement operation conflicts with an existing request",
                    payload.error().retryable(),
                    null
            );
            case TOO_MANY_REQUESTS -> failure(
                    HttpStatus.TOO_MANY_REQUESTS,
                    "AI_BUSY",
                    "AI service is busy",
                    payload.error().retryable(),
                    null
            );
            case BAD_GATEWAY -> failure(
                    HttpStatus.BAD_GATEWAY,
                    "AI_PROTOCOL_ERROR",
                    "AI service reported an upstream protocol error",
                    payload.error().retryable(),
                    null
            );
            case SERVICE_UNAVAILABLE -> failure(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "AI_SERVICE_UNAVAILABLE",
                    "Measurement analysis service is unavailable",
                    payload.error().retryable(),
                    null
            );
            case GATEWAY_TIMEOUT -> failure(
                    HttpStatus.GATEWAY_TIMEOUT,
                    "AI_TIMEOUT",
                    "Measurement analysis timed out",
                    payload.error().retryable(),
                    null
            );
            default -> protocolFailure(null);
        };
    }

    private static void validateSuccess(
            AiMeasurementRequest request,
            org.springframework.http.client.ClientHttpResponse response,
            AiMeasurementResponse result
    ) {
        if (result == null
                || !request.requestId().equals(
                response.getHeaders().getFirst(RequestIds.HEADER_NAME)
        ) || !request.requestId().equals(result.requestId())
                || !request.operationId().equals(result.operationId())
                || isBlank(result.runId()) || isBlank(result.traceId())
                || result.outcome() == null || result.result() == null
                || !Objects.equals(
                request.animalSnapshot().animalId(),
                result.result().animalId()
        ) || isBlank(result.result().summary())
                || result.result().abnormalItems() == null
                || result.result().evidence() == null
                || isBlank(result.result().recommendation())
                || isBlank(result.result().report())
                || result.result().usedDemoHistory()) {
            throw protocolFailure(null);
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static MeasurementClientException protocolFailure(Throwable cause) {
        return failure(
                HttpStatus.BAD_GATEWAY,
                "AI_PROTOCOL_ERROR",
                "AI service response violated the measurement contract",
                false,
                cause
        );
    }

    private static MeasurementClientException failure(
            HttpStatus status,
            String code,
            String message,
            boolean retryable,
            Throwable cause
    ) {
        return new MeasurementClientException(status, code, message, retryable, cause);
    }
}
