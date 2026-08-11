package com.livestock.platform.security;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.UUID;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import com.nimbusds.jose.jwk.source.ImmutableSecret;

public final class JwtService {

    public static final String ACCESS_TOKEN_TYPE = "access";

    private final SecurityProperties properties;
    private final Clock clock;
    private final JwtEncoder encoder;
    private final JwtDecoder decoder;

    public JwtService(SecurityProperties properties) {
        this(properties, Clock.systemUTC());
    }

    public JwtService(SecurityProperties properties, Clock clock) {
        this.properties = properties;
        this.clock = clock;
        SecretKey secretKey = secretKey(properties.jwtSecret());
        this.encoder = new NimbusJwtEncoder(new ImmutableSecret<>(secretKey));

        NimbusJwtDecoder jwtDecoder = NimbusJwtDecoder.withSecretKey(secretKey)
                .macAlgorithm(MacAlgorithm.HS256)
                .build();
        JwtTimestampValidator timestampValidator =
                new JwtTimestampValidator(properties.clockSkew());
        timestampValidator.setClock(clock);
        OAuth2TokenValidator<Jwt> validator = new DelegatingOAuth2TokenValidator<>(
                timestampValidator,
                new JwtIssuerValidator(properties.issuer()),
                audienceValidator(properties.audience()),
                tokenTypeValidator()
        );
        jwtDecoder.setJwtValidator(validator);
        this.decoder = jwtDecoder;
    }

    public AccessToken issueAccessToken(UserPrincipal principal, String sessionId) {
        if (sessionId == null || sessionId.isBlank()) {
            throw new IllegalArgumentException("sessionId must not be blank");
        }
        Instant issuedAt = clock.instant();
        Instant expiresAt = issuedAt.plus(properties.accessTokenTtl());
        Set<String> authorities = new TreeSet<>(principal.authorities());
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(properties.issuer())
                .audience(List.of(properties.audience()))
                .issuedAt(issuedAt)
                .notBefore(issuedAt)
                .expiresAt(expiresAt)
                .subject(principal.userId())
                .id(UUID.randomUUID().toString())
                .claim("token_type", ACCESS_TOKEN_TYPE)
                .claim("sid", sessionId)
                .claim("security_version", principal.securityVersion())
                .claim("authorities", authorities)
                .build();
        JwsHeader header = JwsHeader.with(MacAlgorithm.HS256)
                .type("JWT")
                .build();
        String token = encoder.encode(JwtEncoderParameters.from(header, claims))
                .getTokenValue();
        return new AccessToken(token, expiresAt);
    }

    public DecodedAccessToken decodeAccessToken(String token) {
        Jwt jwt = decoder.decode(token);
        return new DecodedAccessToken(
                jwt.getSubject(),
                jwt.getId(),
                jwt.getClaimAsString("sid"),
                numberClaim(jwt, "security_version"),
                Set.copyOf(stringCollection(jwt.getClaim("authorities"))),
                jwt.getIssuedAt(),
                jwt.getExpiresAt()
        );
    }

    private static SecretKey secretKey(String secret) {
        if (secret == null) {
            throw new IllegalArgumentException("JWT secret must be configured");
        }
        byte[] bytes = secret.getBytes(StandardCharsets.UTF_8);
        if (bytes.length < 32) {
            throw new IllegalArgumentException("JWT secret must contain at least 256 bits");
        }
        return new SecretKeySpec(bytes, "HmacSHA256");
    }

    private static OAuth2TokenValidator<Jwt> audienceValidator(String audience) {
        return jwt -> jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(invalidToken("Invalid audience"));
    }

    private static OAuth2TokenValidator<Jwt> tokenTypeValidator() {
        return jwt -> ACCESS_TOKEN_TYPE.equals(jwt.getClaimAsString("token_type"))
                        && jwt.getSubject() != null
                        && jwt.getId() != null
                        && jwt.getClaimAsString("sid") != null
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(invalidToken("Invalid access token claims"));
    }

    private static OAuth2Error invalidToken(String description) {
        return new OAuth2Error("invalid_token", description, null);
    }

    private static long numberClaim(Jwt jwt, String claimName) {
        Object value = jwt.getClaim(claimName);
        if (value instanceof Number number) {
            return number.longValue();
        }
        throw new IllegalArgumentException("Invalid numeric JWT claim: " + claimName);
    }

    private static Collection<String> stringCollection(Object value) {
        if (!(value instanceof Collection<?> collection)) {
            throw new IllegalArgumentException("Invalid authorities JWT claim");
        }
        return collection.stream()
                .map(item -> {
                    if (!(item instanceof String text)) {
                        throw new IllegalArgumentException("Invalid authority JWT claim");
                    }
                    return text;
                })
                .toList();
    }

    public record AccessToken(String token, Instant expiresAt) {
    }

    public record DecodedAccessToken(
            String userId,
            String jti,
            String sessionId,
            long securityVersion,
            Set<String> authorities,
            Instant issuedAt,
            Instant expiresAt
    ) {
    }
}
