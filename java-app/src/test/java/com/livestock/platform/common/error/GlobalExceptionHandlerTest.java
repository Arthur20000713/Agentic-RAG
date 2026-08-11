package com.livestock.platform.common.error;

import static org.assertj.core.api.Assertions.assertThat;

import com.livestock.platform.common.api.ApiErrorResponse;
import com.livestock.platform.common.web.RequestIds;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.http.ResponseEntity;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.transaction.CannotCreateTransactionException;

class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    void unexpectedErrorsUseSafeMessageAndCurrentRequestId() {
        MDC.put(RequestIds.MDC_KEY, "req_error_0001");

        ResponseEntity<ApiErrorResponse> response =
                handler.handleUnexpected(new IllegalStateException("database-password=secret"));

        assertThat(response.getStatusCode().value()).isEqualTo(500);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().requestId()).isEqualTo("req_error_0001");
        assertThat(response.getBody().error().code()).isEqualTo("INTERNAL_ERROR");
        assertThat(response.getBody().error().message()).doesNotContain("secret");
    }

    @Test
    void datastoreFailuresUseStable503WithoutLeakingDetails() {
        MDC.put(RequestIds.MDC_KEY, "req_datastore_0001");

        ResponseEntity<ApiErrorResponse> response =
                handler.handleDatastoreUnavailable(
                        new DataAccessResourceFailureException(
                                "jdbc:mysql://user:secret@host/database"
                        )
                );

        assertThat(response.getStatusCode().value()).isEqualTo(503);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().requestId()).isEqualTo("req_datastore_0001");
        assertThat(response.getBody().error().code())
                .isEqualTo("DATASTORE_UNAVAILABLE");
        assertThat(response.getBody().error().message()).doesNotContain("secret");
    }

    @Test
    void transactionCreationFailuresUseStable503WithoutLeakingDetails() {
        MDC.put(RequestIds.MDC_KEY, "req_datastore_0002");

        ResponseEntity<ApiErrorResponse> response =
                handler.handleDatastoreUnavailable(
                        new CannotCreateTransactionException(
                                "jdbc:mysql://user:secret@host/database"
                        )
                );

        assertThat(response.getStatusCode().value()).isEqualTo(503);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().requestId()).isEqualTo("req_datastore_0002");
        assertThat(response.getBody().error().code())
                .isEqualTo("DATASTORE_UNAVAILABLE");
        assertThat(response.getBody().error().message()).doesNotContain("secret");
    }
}
