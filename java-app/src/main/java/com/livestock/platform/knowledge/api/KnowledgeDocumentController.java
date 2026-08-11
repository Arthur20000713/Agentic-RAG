package com.livestock.platform.knowledge.api;

import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.common.api.ApiResponse;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.knowledge.service.KnowledgeDocumentService;
import com.livestock.platform.security.UserPrincipal;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Validated
@RestController
@RequestMapping("/api/v1/documents")
public class KnowledgeDocumentController {

    private final KnowledgeDocumentService documentService;

    public KnowledgeDocumentController(KnowledgeDocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping(consumes = "multipart/form-data")
    @PreAuthorize("hasAuthority('DOCUMENT_UPLOAD')")
    public ResponseEntity<ApiResponse<DocumentUploadResponse>> upload(
            @RequestPart("file") MultipartFile file,
            @RequestHeader("Idempotency-Key")
            @Size(min = 8, max = 128)
            @Pattern(regexp = "^[A-Za-z0-9._:-]+$") String idempotencyKey,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest request
    ) {
        DocumentUploadResponse result = documentService.upload(
                file,
                idempotencyKey,
                actor,
                AuditRequestMetadata.from(request)
        );
        return ResponseEntity.accepted()
                .location(URI.create("/api/v1/tasks/" + result.task().id()))
                .header("Idempotent-Replayed", String.valueOf(result.idempotentReplay()))
                .body(ApiResponse.success(RequestIds.current(), result));
    }

    @GetMapping("/{documentId}")
    @PreAuthorize("hasAnyAuthority('DOCUMENT_UPLOAD','TASK_MANAGE')")
    public ApiResponse<KnowledgeDocumentView> get(
            @PathVariable
            @Pattern(regexp = "^doc_[A-Za-z0-9-]{36}$") String documentId,
            @AuthenticationPrincipal UserPrincipal actor
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                documentService.get(documentId, actor)
        );
    }
}
