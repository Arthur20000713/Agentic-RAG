package com.livestock.platform.conversation.api;

import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.common.api.ApiResponse;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.conversation.service.ConversationService;
import com.livestock.platform.conversation.service.AiChatOrchestrationService;
import com.livestock.platform.conversation.service.MessageSubmissionService;
import com.livestock.platform.security.UserPrincipal;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.net.URI;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/conversations")
public class ConversationController {

    public static final String IDEMPOTENT_REPLAYED = "Idempotent-Replayed";

    private final ConversationService conversationService;
    private final MessageSubmissionService messageSubmissionService;
    private final AiChatOrchestrationService aiChatOrchestrationService;

    public ConversationController(
            ConversationService conversationService,
            MessageSubmissionService messageSubmissionService,
            AiChatOrchestrationService aiChatOrchestrationService
    ) {
        this.conversationService = conversationService;
        this.messageSubmissionService = messageSubmissionService;
        this.aiChatOrchestrationService = aiChatOrchestrationService;
    }

    @PostMapping
    @PreAuthorize("hasAuthority('AI_CHAT')")
    public ResponseEntity<ApiResponse<ConversationView>> create(
            @Valid @RequestBody CreateConversationRequest request,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest servletRequest
    ) {
        ConversationView created = conversationService.create(
                request,
                actor,
                AuditRequestMetadata.from(servletRequest)
        );
        return ResponseEntity.created(
                        URI.create("/api/v1/conversations/" + created.id())
                )
                .body(ApiResponse.success(RequestIds.current(), created));
    }

    @GetMapping
    @PreAuthorize(
            "hasAnyAuthority('CONVERSATION_READ_OWN','CONVERSATION_READ_ALL')"
    )
    public ApiResponse<ConversationListResponse> list(
            @RequestParam(defaultValue = "own") String scope,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size,
            @AuthenticationPrincipal UserPrincipal actor
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                conversationService.list(scope, page, size, actor)
        );
    }

    @GetMapping("/{id}")
    @PreAuthorize(
            "hasAnyAuthority('CONVERSATION_READ_OWN','CONVERSATION_READ_ALL')"
    )
    public ApiResponse<ConversationDetailResponse> get(
            @PathVariable @Positive Long id,
            @AuthenticationPrincipal UserPrincipal actor
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                conversationService.get(id, actor)
        );
    }

    @GetMapping("/{id}/messages")
    @PreAuthorize(
            "hasAnyAuthority('CONVERSATION_READ_OWN','CONVERSATION_READ_ALL')"
    )
    public ApiResponse<List<MessageView>> history(
            @PathVariable @Positive Long id,
            @RequestParam(defaultValue = "20") @Min(1) @Max(20) int limit,
            @AuthenticationPrincipal UserPrincipal actor
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                conversationService.boundedHistory(id, limit, actor)
        );
    }

    @PatchMapping("/{id}")
    @PreAuthorize("hasAuthority('AI_CHAT')")
    public ApiResponse<ConversationView> update(
            @PathVariable @Positive Long id,
            @Valid @RequestBody UpdateConversationRequest request,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest servletRequest
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                conversationService.update(
                        id,
                        request,
                        actor,
                        AuditRequestMetadata.from(servletRequest)
                )
        );
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasAuthority('AI_CHAT')")
    public ResponseEntity<Void> delete(
            @PathVariable @Positive Long id,
            @RequestParam @Min(0) long version,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest servletRequest
    ) {
        conversationService.delete(
                id,
                version,
                actor,
                AuditRequestMetadata.from(servletRequest)
        );
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{id}/messages")
    @PreAuthorize("hasAuthority('AI_CHAT')")
    public ResponseEntity<ApiResponse<MessageSubmissionResponse>> submitMessage(
            @PathVariable @Positive Long id,
            @RequestHeader("Idempotency-Key")
            @NotBlank
            @Size(min = 8, max = 128)
            @Pattern(regexp = "^[A-Za-z0-9._:-]+$")
            String idempotencyKey,
            @Valid @RequestBody SubmitMessageRequest request,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest servletRequest
    ) {
        AuditRequestMetadata metadata = AuditRequestMetadata.from(servletRequest);
        aiChatOrchestrationService.requireEnabled();
        MessageSubmissionResponse durableSubmission = messageSubmissionService.submit(
                id,
                idempotencyKey,
                request,
                actor,
                metadata
        );
        MessageSubmissionResponse submission = aiChatOrchestrationService.execute(
                durableSubmission,
                actor,
                metadata
        );
        boolean stillPending = submission.task().status()
                == com.livestock.platform.task.domain.TaskStatus.RUNNING
                || submission.task().status()
                == com.livestock.platform.task.domain.TaskStatus.SUBMIT_UNKNOWN
                || submission.task().status()
                == com.livestock.platform.task.domain.TaskStatus.CREATED;
        ResponseEntity.BodyBuilder response = submission.replayed()
                ? ResponseEntity.ok()
                : stillPending
                ? ResponseEntity.status(HttpStatus.ACCEPTED)
                        .header(
                                HttpHeaders.LOCATION,
                                "/api/v1/tasks/" + submission.task().id()
                        )
                : ResponseEntity.ok();
        if (submission.replayed()) {
            response.header(IDEMPOTENT_REPLAYED, "true");
        }
        return response.body(
                ApiResponse.success(RequestIds.current(), submission)
        );
    }
}
