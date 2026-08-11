package com.livestock.platform.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import java.io.IOException;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
public class PythonAiChatClient {

    private final RestClient restClient;
    private final AiServiceProperties properties;
    private final ObjectMapper objectMapper;
    private final CircuitBreaker circuitBreaker;
    private final Bulkhead bulkhead;
    private final AiCallMetrics metrics;

    public PythonAiChatClient(
            @Qualifier("aiChatRestClient") RestClient restClient,
            AiServiceProperties properties,
            ObjectMapper objectMapper,
            CircuitBreaker pythonAiChatCircuitBreaker,
            Bulkhead pythonAiChatBulkhead,
            AiCallMetrics metrics
    ) {
        this.restClient = restClient;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.circuitBreaker = pythonAiChatCircuitBreaker;
        this.bulkhead = pythonAiChatBulkhead;
        this.metrics = metrics;
    }

    public AiChatResponse chat(AiChatRequest request) {
        return metrics.record(
                AiCallMetrics.Operation.CHAT,
                () -> guardedChat(request),
                result -> result.outcome().name()
        );
    }

    private AiChatResponse guardedChat(AiChatRequest request) {
        Supplier<AiChatResponse> guarded = CircuitBreaker.decorateSupplier(
                circuitBreaker,
                () -> execute(request)
        );
        guarded = Bulkhead.decorateSupplier(bulkhead, guarded);
        try {
            return guarded.get();
        } catch (BulkheadFullException exception) {
            throw failure(
                    "AI_BUSY",
                    null,
                    "AI concurrency limit reached",
                    true,
                    false,
                    false,
                    exception
            );
        } catch (CallNotPermittedException exception) {
            throw failure(
                    "AI_SERVICE_UNAVAILABLE",
                    null,
                    "AI circuit breaker is open",
                    true,
                    false,
                    false,
                    exception
            );
        }
    }

    public Optional<AiChatRun> findRun(String requestId, String operationId) {
        return metrics.record(
                AiCallMetrics.Operation.CHAT_RECONCILIATION,
                () -> findRunWithoutMetrics(requestId, operationId),
                result -> result.map(run -> run.status().name()).orElse("NOT_FOUND")
        );
    }

    private Optional<AiChatRun> findRunWithoutMetrics(
            String requestId,
            String operationId
    ) {
        try {
            return restClient.get()
                    .uri("/internal/v1/ai/runs/{operationId}", operationId)
                    .header(
                            HttpHeaders.AUTHORIZATION,
                            "Bearer " + properties.serviceToken()
                    )
                    .header(RequestIds.HEADER_NAME, requestId)
                    .exchange((httpRequest, response) -> {
                        if (response.getStatusCode().value() == 404) {
                            AiChatClientException failure = remoteFailure(
                                    response.getStatusCode(),
                                    response.getBody(),
                                    response.getHeaders().getFirst(RequestIds.HEADER_NAME),
                                    requestId,
                                    operationId,
                                    false
                            );
                            if ("OPERATION_NOT_FOUND".equals(failure.remoteCode())) {
                                return Optional.empty();
                            }
                            throw failure;
                        }
                        if (!response.getStatusCode().is2xxSuccessful()) {
                            throw remoteFailure(
                                    response.getStatusCode(),
                                    response.getBody(),
                                    response.getHeaders().getFirst(RequestIds.HEADER_NAME),
                                    requestId,
                                    operationId,
                                    false
                            );
                        }
                        AiChatRun run;
                        try {
                            run = objectMapper.readValue(
                                    response.getBody(),
                                    AiChatRun.class
                            );
                        } catch (IOException exception) {
                            throw protocolFailure(exception);
                        }
                        validateRun(
                                requestId,
                                operationId,
                                response.getHeaders().getFirst(RequestIds.HEADER_NAME),
                                run
                        );
                        return Optional.of(run);
                    });
        } catch (AiChatClientException exception) {
            throw exception;
        } catch (ResourceAccessException exception) {
            throw failure(
                    "AI_RECONCILIATION_UNAVAILABLE",
                    null,
                    "AI execution reconciliation was unavailable",
                    true,
                    false,
                    true,
                    exception
            );
        } catch (RestClientException exception) {
            throw failure(
                    "AI_SERVICE_UNAVAILABLE",
                    null,
                    "AI reconciliation request failed",
                    true,
                    false,
                    true,
                    exception
            );
        }
    }

    private AiChatResponse execute(AiChatRequest request) {
        try {
            return restClient.post()
                    .uri("/internal/v1/ai/chat")
                    .header(
                            HttpHeaders.AUTHORIZATION,
                            "Bearer " + properties.serviceToken()
                    )
                    .header(RequestIds.HEADER_NAME, request.requestId())
                    .header("Idempotency-Key", request.operationId())
                    .body(request)
                    .exchange((httpRequest, response) -> {
                        if (!response.getStatusCode().is2xxSuccessful()) {
                            throw remoteFailure(
                                    response.getStatusCode(),
                                    response.getBody(),
                                    response.getHeaders().getFirst(RequestIds.HEADER_NAME),
                                    request.requestId(),
                                    request.operationId(),
                                    true
                            );
                        }
                        AiChatResponse result;
                        try {
                            result = objectMapper.readValue(
                                    response.getBody(),
                                    AiChatResponse.class
                            );
                        } catch (IOException exception) {
                            throw chatProtocolFailure(exception);
                        }
                        try {
                            validateResponse(
                                    request,
                                    response.getHeaders().getFirst(RequestIds.HEADER_NAME),
                                    result
                            );
                        } catch (AiChatClientException exception) {
                            throw chatProtocolFailure(exception);
                        }
                        return result;
                    });
        } catch (AiChatClientException exception) {
            throw exception;
        } catch (ResourceAccessException exception) {
            throw failure(
                    "AI_SUBMISSION_UNKNOWN",
                    null,
                    "AI chat response was not received",
                    true,
                    true,
                    true,
                    exception
            );
        } catch (RestClientException exception) {
            throw failure(
                    "AI_SERVICE_UNAVAILABLE",
                    null,
                    "AI service request failed",
                    true,
                    false,
                    true,
                    exception
            );
        }
    }

    private AiChatClientException remoteFailure(
            HttpStatusCode status,
            java.io.InputStream body,
            String responseRequestId,
            String expectedRequestId,
            String expectedOperationId,
            boolean chatSubmission
    ) {
        AiServiceErrorResponse errorResponse;
        try {
            errorResponse = objectMapper.readValue(body, AiServiceErrorResponse.class);
        } catch (IOException exception) {
            throw remoteProtocolFailure(status, chatSubmission, exception);
        }
        if (errorResponse == null
                || errorResponse.error() == null
                || errorResponse.error().code() == null
                || errorResponse.error().code().isBlank()
                || errorResponse.error().message() == null
                || errorResponse.error().message().isBlank()
                || !expectedRequestId.equals(responseRequestId)
                || !expectedRequestId.equals(errorResponse.requestId())
                || (errorResponse.operationId() != null
                && !expectedOperationId.equals(errorResponse.operationId()))) {
            throw remoteProtocolFailure(status, chatSubmission, null);
        }
        String remoteCode = errorResponse.error().code();
        boolean remoteRetryable = errorResponse.error().retryable();
        int value = status.value();
        if (value == 400 || value == 422) {
            return failure(
                    "AI_REQUEST_REJECTED",
                    remoteCode,
                    "AI service rejected the request",
                    false,
                    false,
                    false,
                    null
            );
        }
        if (value == 401 || value == 403) {
            return failure(
                    "AI_SERVICE_AUTH_FAILED",
                    remoteCode,
                    "AI service authentication failed",
                    false,
                    false,
                    false,
                    null
            );
        }
        if (value == 409) {
            return failure(
                    "AI_CONFLICT",
                    remoteCode,
                    "AI operation conflicts with an existing execution",
                    false,
                    false,
                    false,
                    null
            );
        }
        if (value == 429) {
            return failure(
                    "AI_BUSY",
                    remoteCode,
                    "AI service is busy",
                    remoteRetryable,
                    false,
                    false,
                    null
            );
        }
        if (value == 504) {
            return failure(
                    "AI_TIMEOUT",
                    remoteCode,
                    "AI chat exceeded its deadline",
                    remoteRetryable,
                    false,
                    true,
                    null
            );
        }
        if (value == 502) {
            return failure(
                    "AI_PROTOCOL_ERROR",
                    remoteCode,
                    "AI dependency returned an invalid response",
                    remoteRetryable,
                    false,
                    true,
                    null
            );
        }
        boolean executionStoreUnknown =
                "EXECUTION_STORE_UNAVAILABLE".equals(remoteCode);
        return failure(
                "AI_SERVICE_UNAVAILABLE",
                remoteCode,
                "AI service is unavailable",
                remoteRetryable || status.is5xxServerError(),
                chatSubmission && executionStoreUnknown,
                status.is5xxServerError(),
                null
        );
    }

    private static AiChatClientException remoteProtocolFailure(
            HttpStatusCode status,
            boolean chatSubmission,
            Throwable cause
    ) {
        boolean serverFailure = status.is5xxServerError();
        return failure(
                "AI_PROTOCOL_ERROR",
                null,
                "AI service returned an invalid error response",
                false,
                chatSubmission && serverFailure,
                serverFailure,
                cause
        );
    }

    private static void validateResponse(
            AiChatRequest request,
            String responseRequestId,
            AiChatResponse response
    ) {
        validateResponsePayload(response);
        if (!request.requestId().equals(responseRequestId)
                || !request.requestId().equals(response.requestId())
                || !request.operationId().equals(response.operationId())
                || response.contextVersion() != request.contextVersion() + 1) {
            throw protocolFailure();
        }
    }

    private static void validateResponsePayload(AiChatResponse response) {
        if (response == null
                || response.requestId() == null
                || response.requestId().isBlank()
                || response.operationId() == null
                || response.operationId().isBlank()
                || response.runId() == null
                || response.runId().isBlank()
                || response.outcome() == null
                || response.answer() == null
                || response.answer().isBlank()
                || response.intent() == null
                || response.intent().isBlank()
                || response.riskLevel() == null
                || response.evidenceStatus() == null
                || response.nextContext() == null
                || response.nextContext().path("schemaVersion").asInt(0) < 1
                || response.safety() == null
                || response.safety().decision() == null
                || response.traceId() == null
                || response.traceId().isBlank()
                || response.sources() == null
                || response.followUpQuestions() == null
                || response.toolsUsed() == null) {
            throw protocolFailure();
        }
        if ((response.evidenceStatus() != AiChatResponse.EvidenceStatus.SUPPORTED
                || response.safety().decision() != AiChatResponse.Decision.ALLOWED)
                && !response.sources().isEmpty()) {
            throw protocolFailure();
        }
        boolean invalidSource = response.sources().stream().anyMatch(source ->
                source == null
                        || source.collection() == null
                        || source.collection().isBlank()
                        || source.documentId() == null
                        || source.title() == null
                        || source.title().isBlank()
                        || source.chunkId() == null
                        || source.chunkId().isBlank()
                        || !Double.isFinite(source.score())
                        || source.score() < 0
                        || source.score() > 1
        );
        if (invalidSource) {
            throw protocolFailure();
        }
    }

    private static void validateRun(
            String requestId,
            String operationId,
            String responseRequestId,
            AiChatRun run
    ) {
        if (run == null
                || run.status() == null
                || run.runId() == null
                || run.runId().isBlank()
                || run.createdAt() == null
                || run.updatedAt() == null
                || run.expiresAt() == null) {
            throw protocolFailure();
        }
        boolean invalidState = switch (run.status()) {
            case RUNNING -> run.result() != null || run.error() != null;
            case SUCCEEDED -> run.result() == null || run.error() != null;
            case FAILED -> run.result() != null || run.error() == null;
        };
        if (!requestId.equals(responseRequestId)
                || !requestId.equals(run.requestId())
                || !operationId.equals(run.operationId())
                || !"AI_CHAT".equals(run.type())
                || invalidState) {
            throw protocolFailure();
        }
        if (run.result() != null
                && (!operationId.equals(run.result().operationId())
                || !run.runId().equals(run.result().runId()))) {
            throw protocolFailure();
        }
        if (run.result() != null) {
            validateResponsePayload(run.result());
        }
        if (run.error() != null
                && (run.error().code() == null
                || run.error().code().isBlank()
                || run.error().message() == null
                || run.error().message().isBlank())) {
            throw protocolFailure();
        }
    }

    private static AiChatClientException protocolFailure() {
        return protocolFailure(null);
    }

    private static AiChatClientException protocolFailure(Throwable cause) {
        return failure(
                "AI_PROTOCOL_ERROR",
                null,
                "AI service response violated the chat contract",
                false,
                false,
                false,
                cause
        );
    }

    private static AiChatClientException chatProtocolFailure(Throwable cause) {
        return failure(
                "AI_PROTOCOL_ERROR",
                null,
                "AI chat response violated the contract after submission",
                false,
                true,
                true,
                cause
        );
    }

    private static AiChatClientException failure(
            String code,
            String remoteCode,
            String message,
            boolean retryable,
            boolean submissionUnknown,
            boolean circuitFailure,
            Throwable cause
    ) {
        return new AiChatClientException(
                Objects.requireNonNull(code),
                remoteCode,
                message,
                retryable,
                submissionUnknown,
                circuitFailure,
                cause
        );
    }
}
