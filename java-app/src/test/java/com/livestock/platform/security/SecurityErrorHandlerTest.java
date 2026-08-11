package com.livestock.platform.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.web.RequestIds;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.BadCredentialsException;

class SecurityErrorHandlerTest {

    private ObjectMapper objectMapper;
    private SecurityErrorWriter writer;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper().findAndRegisterModules();
        writer = new SecurityErrorWriter(objectMapper);
        MDC.put(RequestIds.MDC_KEY, "req_security_0001");
    }

    @AfterEach
    void clearMdc() {
        MDC.clear();
    }

    @Test
    void authenticationFailureUsesSafeUnifiedResponse() throws Exception {
        MockHttpServletResponse response = new MockHttpServletResponse();
        ApiAuthenticationEntryPoint entryPoint = new ApiAuthenticationEntryPoint(writer);

        entryPoint.commence(
                new MockHttpServletRequest(),
                response,
                new BadCredentialsException("token=secret")
        );

        JsonNode body = objectMapper.readTree(response.getContentAsByteArray());
        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentType()).startsWith("application/json");
        assertThat(body.path("requestId").asText()).isEqualTo("req_security_0001");
        assertThat(body.path("error").path("code").asText())
                .isEqualTo("AUTHENTICATION_REQUIRED");
        assertThat(response.getContentAsString()).doesNotContain("secret");
    }

    @Test
    void authorizationFailureUsesSafeUnifiedResponse() throws Exception {
        MockHttpServletResponse response = new MockHttpServletResponse();
        ApiAccessDeniedHandler deniedHandler = new ApiAccessDeniedHandler(writer);

        deniedHandler.handle(
                new MockHttpServletRequest(),
                response,
                new AccessDeniedException("database-password=secret")
        );

        JsonNode body = objectMapper.readTree(response.getContentAsByteArray());
        assertThat(response.getStatus()).isEqualTo(403);
        assertThat(body.path("requestId").asText()).isEqualTo("req_security_0001");
        assertThat(body.path("error").path("code").asText()).isEqualTo("ACCESS_DENIED");
        assertThat(response.getContentAsString()).doesNotContain("secret");
    }
}
