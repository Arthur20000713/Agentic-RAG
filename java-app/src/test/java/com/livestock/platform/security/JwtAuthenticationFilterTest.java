package com.livestock.platform.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.transaction.CannotCreateTransactionException;

class JwtAuthenticationFilterTest {

    private static final Instant NOW = Instant.parse("2026-07-30T00:00:00Z");

    private ObjectMapper objectMapper;
    private JwtService jwtService;
    private RedisRefreshTokenFamilyStore refreshStore;
    private UserSecurityReader userReader;
    private JwtAuthenticationFilter filter;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper().findAndRegisterModules();
        jwtService = new JwtService(
                properties(),
                Clock.fixed(NOW, ZoneOffset.UTC)
        );
        refreshStore = mock(RedisRefreshTokenFamilyStore.class);
        userReader = mock(UserSecurityReader.class);
        SecurityErrorWriter writer = new SecurityErrorWriter(objectMapper);
        filter = new JwtAuthenticationFilter(
                jwtService,
                refreshStore,
                userReader,
                new ApiAuthenticationEntryPoint(writer),
                writer
        );
    }

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void authenticatesOnlyAgainstActiveFamilyAndCurrentUserVersion() throws Exception {
        UserPrincipal principal =
                new UserPrincipal("user-123", "alice", 3L, Set.of("AI_CHAT"));
        String token = jwtService.issueAccessToken(principal, "family-123").token();
        when(refreshStore.isFamilyActive("family-123")).thenReturn(true);
        when(userReader.findActiveUser("user-123")).thenReturn(Optional.of(principal));
        MockHttpServletRequest request = requestWithToken(token);
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicBoolean called = new AtomicBoolean();

        filter.doFilter(request, response, (req, res) -> {
            called.set(true);
            assertThat(SecurityContextHolder.getContext().getAuthentication().isAuthenticated())
                    .isTrue();
            assertThat(SecurityContextHolder.getContext().getAuthentication().getAuthorities())
                    .extracting(Object::toString)
                    .containsExactly("AI_CHAT");
        });

        assertThat(called).isTrue();
        assertThat(response.getStatus()).isEqualTo(200);
        assertThat(SecurityContextHolder.getContext().getAuthentication()).isNull();
    }

    @Test
    void rejectsStaleSecurityVersionWithUnified401() throws Exception {
        UserPrincipal tokenPrincipal =
                new UserPrincipal("user-123", "alice", 3L, Set.of("AI_CHAT"));
        UserPrincipal currentPrincipal =
                new UserPrincipal("user-123", "alice", 4L, Set.of("AI_CHAT"));
        String token = jwtService.issueAccessToken(tokenPrincipal, "family-123").token();
        when(refreshStore.isFamilyActive("family-123")).thenReturn(true);
        when(userReader.findActiveUser("user-123"))
                .thenReturn(Optional.of(currentPrincipal));
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(
                requestWithToken(token),
                response,
                (req, res) -> {
                    throw new AssertionError("filter chain must not be called");
                }
        );

        JsonNode body = objectMapper.readTree(response.getContentAsByteArray());
        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(body.path("error").path("code").asText())
                .isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void redisFailureReturnsFailClosed503() throws Exception {
        UserPrincipal principal =
                new UserPrincipal("user-123", "alice", 3L, Set.of("AI_CHAT"));
        String token = jwtService.issueAccessToken(principal, "family-123").token();
        when(refreshStore.isFamilyActive("family-123"))
                .thenThrow(new SecurityStateUnavailableException("offline"));
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(
                requestWithToken(token),
                response,
                (req, res) -> {
                    throw new AssertionError("filter chain must not be called");
                }
        );

        JsonNode body = objectMapper.readTree(response.getContentAsByteArray());
        assertThat(response.getStatus()).isEqualTo(503);
        assertThat(body.path("error").path("code").asText())
                .isEqualTo("AUTH_STATE_UNAVAILABLE");
    }

    @Test
    void mysqlFailureReturnsFailClosed503() throws Exception {
        UserPrincipal principal =
                new UserPrincipal("user-123", "alice", 3L, Set.of("AI_CHAT"));
        String token = jwtService.issueAccessToken(principal, "family-123").token();
        when(refreshStore.isFamilyActive("family-123")).thenReturn(true);
        when(userReader.findActiveUser("user-123"))
                .thenThrow(new DataAccessResourceFailureException("offline"));
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(
                requestWithToken(token),
                response,
                (req, res) -> {
                    throw new AssertionError("filter chain must not be called");
                }
        );

        JsonNode body = objectMapper.readTree(response.getContentAsByteArray());
        assertThat(response.getStatus()).isEqualTo(503);
        assertThat(body.path("error").path("code").asText())
                .isEqualTo("DATASTORE_UNAVAILABLE");
    }

    @Test
    void mysqlTransactionCreationFailureReturnsFailClosed503() throws Exception {
        UserPrincipal principal =
                new UserPrincipal("user-123", "alice", 3L, Set.of("AI_CHAT"));
        String token = jwtService.issueAccessToken(principal, "family-123").token();
        when(refreshStore.isFamilyActive("family-123")).thenReturn(true);
        when(userReader.findActiveUser("user-123"))
                .thenThrow(new CannotCreateTransactionException("offline"));
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(
                requestWithToken(token),
                response,
                (req, res) -> {
                    throw new AssertionError("filter chain must not be called");
                }
        );

        JsonNode body = objectMapper.readTree(response.getContentAsByteArray());
        assertThat(response.getStatus()).isEqualTo(503);
        assertThat(body.path("error").path("code").asText())
                .isEqualTo("DATASTORE_UNAVAILABLE");
    }

    @Test
    void malformedAuthorizationSchemeReturnsUnified401() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(HttpHeaders.AUTHORIZATION, "Basic credentials");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(
                request,
                response,
                (req, res) -> {
                    throw new AssertionError("filter chain must not be called");
                }
        );

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentAsString()).doesNotContain("credentials");
    }

    private static MockHttpServletRequest requestWithToken(String token) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(HttpHeaders.AUTHORIZATION, "Bearer " + token);
        return request;
    }

    private static SecurityProperties properties() {
        return new SecurityProperties(
                "0123456789abcdef0123456789abcdef",
                "issuer-a",
                "audience-a",
                Duration.ofMinutes(5),
                Duration.ofMinutes(10),
                Duration.ZERO,
                List.of(),
                "test:auth:"
        );
    }
}
