package com.livestock.platform.common.error;

import com.livestock.platform.common.api.ApiErrorResponse;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.security.SecurityAuditRecorder;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DataAccessException;
import org.springframework.transaction.CannotCreateTransactionException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger LOGGER = LoggerFactory.getLogger(GlobalExceptionHandler.class);
    private SecurityAuditRecorder securityAuditRecorder;

    @Autowired
    void setSecurityAuditRecorder(SecurityAuditRecorder securityAuditRecorder) {
        this.securityAuditRecorder = securityAuditRecorder;
    }

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ApiErrorResponse> handleApiException(ApiException exception) {
        return ResponseEntity.status(exception.status()).body(
                ApiErrorResponse.of(
                        RequestIds.current(),
                        exception.code(),
                        exception.getMessage()
                )
        );
    }

    @ExceptionHandler({MethodArgumentNotValidException.class, ConstraintViolationException.class})
    public ResponseEntity<ApiErrorResponse> handleValidation(Exception exception) {
        return ResponseEntity.badRequest().body(
                ApiErrorResponse.of(
                        RequestIds.current(),
                        "VALIDATION_FAILED",
                        "Request validation failed"
                )
        );
    }

    @ExceptionHandler({
            HttpMessageNotReadableException.class,
            MethodArgumentTypeMismatchException.class,
            MissingServletRequestParameterException.class,
            MissingRequestHeaderException.class
    })
    public ResponseEntity<ApiErrorResponse> handleInvalidRequest(Exception exception) {
        return ResponseEntity.badRequest().body(
                ApiErrorResponse.of(
                        RequestIds.current(),
                        "INVALID_REQUEST",
                        "The request could not be parsed"
                )
        );
    }

    @ExceptionHandler(ObjectOptimisticLockingFailureException.class)
    public ResponseEntity<ApiErrorResponse> handleVersionConflict(
            ObjectOptimisticLockingFailureException exception
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                ApiErrorResponse.of(
                        RequestIds.current(),
                        "VERSION_CONFLICT",
                        "The resource changed before this request completed"
                )
        );
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiErrorResponse> handleDataConflict(
            DataIntegrityViolationException exception
    ) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                ApiErrorResponse.of(
                        RequestIds.current(),
                        "DATA_CONFLICT",
                        "The request conflicts with existing data"
                )
        );
    }

    @ExceptionHandler({
            DataAccessException.class,
            CannotCreateTransactionException.class
    })
    public ResponseEntity<ApiErrorResponse> handleDatastoreUnavailable(
            Exception exception
    ) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(
                ApiErrorResponse.of(
                        RequestIds.current(),
                        "DATASTORE_UNAVAILABLE",
                        "Business data is temporarily unavailable"
                )
        );
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ApiErrorResponse> handleAccessDenied(
            AccessDeniedException exception,
            HttpServletRequest request
    ) {
        if (securityAuditRecorder != null) {
            securityAuditRecorder.recordDenied(request, "FORBIDDEN");
        }
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(
                ApiErrorResponse.of(
                        RequestIds.current(),
                        "ACCESS_DENIED",
                        "Access is denied"
                )
        );
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiErrorResponse> handleUnexpected(Exception exception) {
        LOGGER.error("Unhandled request failure type={}", exception.getClass().getName());
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(
                ApiErrorResponse.of(
                        RequestIds.current(),
                        "INTERNAL_ERROR",
                        "The service could not process the request"
                )
        );
    }
}
