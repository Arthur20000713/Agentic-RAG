package com.livestock.platform.auth.api;

import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.auth.service.AuthenticationService;
import com.livestock.platform.common.api.ApiResponse;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.security.UserPrincipal;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthenticationController {

    private final AuthenticationService authenticationService;

    public AuthenticationController(AuthenticationService authenticationService) {
        this.authenticationService = authenticationService;
    }

    @PostMapping("/login")
    public ResponseEntity<ApiResponse<TokenPairResponse>> login(
            @Valid @RequestBody LoginRequest request,
            HttpServletRequest servletRequest
    ) {
        TokenPairResponse tokens = authenticationService.login(
                request.username(),
                request.password(),
                AuditRequestMetadata.from(servletRequest)
        );
        return noStore(ApiResponse.success(RequestIds.current(), tokens));
    }

    @PostMapping("/refresh")
    public ResponseEntity<ApiResponse<TokenPairResponse>> refresh(
            @Valid @RequestBody RefreshTokenRequest request,
            HttpServletRequest servletRequest
    ) {
        TokenPairResponse tokens = authenticationService.refresh(
                request.refreshToken(),
                AuditRequestMetadata.from(servletRequest)
        );
        return noStore(ApiResponse.success(RequestIds.current(), tokens));
    }

    @PostMapping("/logout")
    public ResponseEntity<ApiResponse<LogoutResponse>> logout(
            @RequestHeader(HttpHeaders.AUTHORIZATION) String authorization,
            @AuthenticationPrincipal UserPrincipal principal,
            HttpServletRequest servletRequest
    ) {
        authenticationService.logout(
                bearerToken(authorization),
                principal,
                AuditRequestMetadata.from(servletRequest)
        );
        return noStore(
                ApiResponse.success(RequestIds.current(), new LogoutResponse(true))
        );
    }

    private static String bearerToken(String authorization) {
        return authorization.substring("Bearer ".length()).trim();
    }

    private static <T> ResponseEntity<ApiResponse<T>> noStore(ApiResponse<T> response) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header(HttpHeaders.PRAGMA, "no-cache")
                .body(response);
    }
}
