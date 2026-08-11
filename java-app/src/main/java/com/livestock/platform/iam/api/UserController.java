package com.livestock.platform.iam.api;

import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.common.api.ApiResponse;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.iam.service.UserAdministrationService;
import com.livestock.platform.security.UserPrincipal;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/users")
public class UserController {

    private final UserAdministrationService userAdministrationService;

    public UserController(UserAdministrationService userAdministrationService) {
        this.userAdministrationService = userAdministrationService;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('USER_MANAGE')")
    public ApiResponse<UserListResponse> list(
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                userAdministrationService.list(page, size)
        );
    }

    @GetMapping("/{id}")
    public ApiResponse<UserView> get(
            @PathVariable Long id,
            @AuthenticationPrincipal UserPrincipal actor
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                userAdministrationService.getVisibleUser(id, actor)
        );
    }

    @PostMapping
    @PreAuthorize("hasAuthority('USER_MANAGE')")
    public ResponseEntity<ApiResponse<UserView>> create(
            @Valid @RequestBody CreateUserRequest request,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest servletRequest
    ) {
        UserView created = userAdministrationService.create(
                request,
                actor,
                AuditRequestMetadata.from(servletRequest)
        );
        return ResponseEntity.created(URI.create("/api/v1/users/" + created.id()))
                .body(ApiResponse.success(RequestIds.current(), created));
    }

    @PatchMapping("/{id}/status")
    @PreAuthorize("hasAuthority('USER_MANAGE')")
    public ApiResponse<UserView> changeStatus(
            @PathVariable Long id,
            @Valid @RequestBody ChangeUserStatusRequest request,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest servletRequest
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                userAdministrationService.changeStatus(
                        id,
                        request,
                        actor,
                        AuditRequestMetadata.from(servletRequest)
                )
        );
    }

    @PutMapping("/{id}/roles")
    @PreAuthorize("hasAuthority('USER_MANAGE')")
    public ApiResponse<UserView> replaceRoles(
            @PathVariable Long id,
            @Valid @RequestBody ReplaceUserRolesRequest request,
            @AuthenticationPrincipal UserPrincipal actor,
            HttpServletRequest servletRequest
    ) {
        return ApiResponse.success(
                RequestIds.current(),
                userAdministrationService.replaceRoles(
                        id,
                        request,
                        actor,
                        AuditRequestMetadata.from(servletRequest)
                )
        );
    }
}
