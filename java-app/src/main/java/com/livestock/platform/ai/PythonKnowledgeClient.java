package com.livestock.platform.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import java.io.IOException;
import java.util.Objects;
import java.util.Optional;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component
public class PythonKnowledgeClient {

    private final RestClient restClient;
    private final AiServiceProperties properties;
    private final ObjectMapper objectMapper;
    private final AiCallMetrics metrics;

    public PythonKnowledgeClient(
            RestClient aiServiceRestClient,
            AiServiceProperties properties,
            ObjectMapper objectMapper,
            AiCallMetrics metrics
    ) {
        this.restClient = aiServiceRestClient;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.metrics = metrics;
    }

    public KnowledgeIngestionAccepted submit(KnowledgeIngestionRequest request) {
        return metrics.record(
                AiCallMetrics.Operation.DOCUMENT_INDEX_SUBMIT,
                () -> submitWithoutMetrics(request),
                accepted -> accepted.status().name()
        );
    }

    private KnowledgeIngestionAccepted submitWithoutMetrics(
            KnowledgeIngestionRequest request
    ) {
        try {
            return restClient.post()
                    .uri("/internal/v1/ai/knowledge/ingestions")
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + properties.serviceToken())
                    .header(RequestIds.HEADER_NAME, request.requestId())
                    .header("Idempotency-Key", request.operationId())
                    .body(request)
                    .exchange((httpRequest, response) -> {
                        if (!response.getStatusCode().is2xxSuccessful()) {
                            throw remoteFailure(response.getStatusCode(), true);
                        }
                        KnowledgeIngestionAccepted accepted;
                        try {
                            accepted = objectMapper.readValue(
                                    response.getBody(),
                                    KnowledgeIngestionAccepted.class
                            );
                        } catch (IOException exception) {
                            throw protocolFailure(true, exception);
                        }
                        String location = response.getHeaders().getFirst(HttpHeaders.LOCATION);
                        if (!request.requestId().equals(
                                response.getHeaders().getFirst(RequestIds.HEADER_NAME)
                        ) || !request.requestId().equals(accepted.requestId())
                                || !request.operationId().equals(accepted.operationId())
                                || !"DOCUMENT_INDEX".equals(accepted.type())
                                || accepted.runId() == null || accepted.runId().isBlank()
                                || accepted.status() == null
                                || !Objects.equals(
                                location,
                                "/internal/v1/ai/operations/" + request.operationId()
                        )) {
                            throw protocolFailure(true, null);
                        }
                        return accepted;
                    });
        } catch (KnowledgeClientException exception) {
            throw exception;
        } catch (ResourceAccessException exception) {
            throw failure(
                    "DOCUMENT_SUBMISSION_UNKNOWN",
                    "Document ingestion response was not received",
                    true,
                    true,
                    exception
            );
        } catch (RestClientException exception) {
            throw failure(
                    "AI_SERVICE_UNAVAILABLE",
                    "Document ingestion request failed",
                    false,
                    true,
                    exception
            );
        }
    }

    public Optional<DocumentIndexOperation> findOperation(
            String requestId,
            String operationId
    ) {
        return metrics.record(
                AiCallMetrics.Operation.DOCUMENT_INDEX_RECONCILIATION,
                () -> findOperationWithoutMetrics(requestId, operationId),
                result -> result.map(operation -> operation.status().name())
                        .orElse("NOT_FOUND")
        );
    }

    private Optional<DocumentIndexOperation> findOperationWithoutMetrics(
            String requestId,
            String operationId
    ) {
        try {
            return restClient.get()
                    .uri("/internal/v1/ai/operations/{operationId}", operationId)
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + properties.serviceToken())
                    .header(RequestIds.HEADER_NAME, requestId)
                    .exchange((httpRequest, response) -> {
                        if (response.getStatusCode().value() == 404) {
                            return Optional.empty();
                        }
                        if (!response.getStatusCode().is2xxSuccessful()) {
                            throw remoteFailure(response.getStatusCode(), false);
                        }
                        DocumentIndexOperation operation;
                        try {
                            operation = objectMapper.readValue(
                                    response.getBody(),
                                    DocumentIndexOperation.class
                            );
                        } catch (IOException exception) {
                            throw protocolFailure(false, exception);
                        }
                        validateOperation(requestId, operationId, response, operation);
                        return Optional.of(operation);
                    });
        } catch (KnowledgeClientException exception) {
            throw exception;
        } catch (RestClientException exception) {
            throw failure(
                    "AI_RECONCILIATION_UNAVAILABLE",
                    "Document ingestion reconciliation is unavailable",
                    false,
                    true,
                    exception
            );
        }
    }

    private static void validateOperation(
            String requestId,
            String operationId,
            org.springframework.http.client.ClientHttpResponse response,
            DocumentIndexOperation operation
    ) {
        if (operation == null
                || !requestId.equals(response.getHeaders().getFirst(RequestIds.HEADER_NAME))
                || !requestId.equals(operation.requestId())
                || !operationId.equals(operation.operationId())
                || !"DOCUMENT_INDEX".equals(operation.type())
                || operation.runId() == null || operation.runId().isBlank()
                || operation.status() == null
                || operation.progress() < 0 || operation.progress() > 100
                || operation.createdAt() == null
                || operation.updatedAt() == null
                || operation.expiresAt() == null) {
            throw protocolFailure(false, null);
        }
        boolean invalidState = switch (operation.status()) {
            case ACCEPTED, RUNNING -> operation.result() != null || operation.error() != null;
            case SUCCEEDED -> operation.result() == null || operation.error() != null
                    || operation.progress() != 100;
            case FAILED, TIMED_OUT, CANCELLED -> operation.result() != null
                    || operation.error() == null || operation.progress() != 100;
        };
        if (invalidState) {
            throw protocolFailure(false, null);
        }
    }

    private static KnowledgeClientException remoteFailure(
            HttpStatusCode status,
            boolean submission
    ) {
        boolean serverFailure = status.is5xxServerError();
        return failure(
                serverFailure ? "AI_SERVICE_UNAVAILABLE" : "DOCUMENT_SUBMISSION_REJECTED",
                serverFailure
                        ? "AI service is unavailable"
                        : "AI service rejected the document ingestion request",
                submission && serverFailure,
                serverFailure,
                null
        );
    }

    private static KnowledgeClientException protocolFailure(
            boolean submission,
            Throwable cause
    ) {
        return failure(
                "AI_PROTOCOL_ERROR",
                "AI service response violated the document ingestion contract",
                submission,
                false,
                cause
        );
    }

    private static KnowledgeClientException failure(
            String code,
            String message,
            boolean submissionUnknown,
            boolean retryable,
            Throwable cause
    ) {
        return new KnowledgeClientException(
                code,
                message,
                submissionUnknown,
                retryable,
                cause
        );
    }
}
