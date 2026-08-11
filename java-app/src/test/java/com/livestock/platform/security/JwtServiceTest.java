package com.livestock.platform.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtException;

class JwtServiceTest {

    private static final String SECRET = "0123456789abcdef0123456789abcdef";
    private static final Instant NOW = Instant.parse("2026-07-30T00:00:00Z");

    @Test
    void issuesAndValidatesPinnedAccessTokenClaims() {
        JwtService service = service(properties(SECRET, "issuer-a", "audience-a"), NOW);
        UserPrincipal principal = new UserPrincipal(
                "user-123",
                "alice",
                7L,
                Set.of("AI_CHAT", "CONVERSATION_READ_OWN")
        );

        JwtService.AccessToken issued = service.issueAccessToken(principal, "family-123");
        JwtService.DecodedAccessToken decoded = service.decodeAccessToken(issued.token());

        assertThat(decoded.userId()).isEqualTo("user-123");
        assertThat(decoded.jti()).isNotBlank();
        assertThat(decoded.sessionId()).isEqualTo("family-123");
        assertThat(decoded.securityVersion()).isEqualTo(7L);
        assertThat(decoded.authorities())
                .containsExactlyInAnyOrder("AI_CHAT", "CONVERSATION_READ_OWN");
        assertThat(decoded.issuedAt()).isEqualTo(NOW);
        assertThat(decoded.expiresAt()).isEqualTo(NOW.plusSeconds(300));
    }

    @Test
    void rejectsTamperedSignature() {
        JwtService service = service(properties(SECRET, "issuer-a", "audience-a"), NOW);
        String token = service.issueAccessToken(principal(), "family-123").token();
        String[] segments = token.split("\\.");
        char replacement = segments[2].charAt(0) == 'A' ? 'B' : 'A';
        segments[2] = replacement + segments[2].substring(1);

        assertThatThrownBy(() -> service.decodeAccessToken(String.join(".", segments)))
                .isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsWrongIssuerAndAudience() {
        JwtService expected = service(properties(SECRET, "issuer-a", "audience-a"), NOW);
        JwtService wrongIssuer = service(properties(SECRET, "issuer-b", "audience-a"), NOW);
        JwtService wrongAudience = service(properties(SECRET, "issuer-a", "audience-b"), NOW);

        assertThatThrownBy(() -> expected.decodeAccessToken(
                wrongIssuer.issueAccessToken(principal(), "family-123").token()
        )).isInstanceOf(JwtException.class);
        assertThatThrownBy(() -> expected.decodeAccessToken(
                wrongAudience.issueAccessToken(principal(), "family-123").token()
        )).isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsExpiredAccessToken() {
        JwtService issuer = service(properties(SECRET, "issuer-a", "audience-a"), NOW);
        String token = issuer.issueAccessToken(principal(), "family-123").token();
        JwtService verifier = service(
                properties(SECRET, "issuer-a", "audience-a"),
                NOW.plus(Duration.ofMinutes(6))
        );

        assertThatThrownBy(() -> verifier.decodeAccessToken(token))
                .isInstanceOf(JwtException.class);
    }

    @Test
    void rejectsSecretsShorterThanHs256KeySize() {
        SecurityProperties weak = properties("too-short", "issuer-a", "audience-a");

        assertThatThrownBy(() -> service(weak, NOW))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("256 bits");
    }

    private static JwtService service(SecurityProperties properties, Instant now) {
        return new JwtService(properties, Clock.fixed(now, ZoneOffset.UTC));
    }

    private static UserPrincipal principal() {
        return new UserPrincipal("user-123", "alice", 1L, Set.of("AI_CHAT"));
    }

    private static SecurityProperties properties(
            String secret,
            String issuer,
            String audience
    ) {
        return new SecurityProperties(
                secret,
                issuer,
                audience,
                Duration.ofMinutes(5),
                Duration.ofDays(7),
                Duration.ZERO,
                List.of("http://127.0.0.1:8080"),
                "test:auth:"
        );
    }
}
