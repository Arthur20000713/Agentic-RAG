package com.livestock.platform.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.UUID;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public final class RedisRefreshTokenFamilyStore {

    private static final int TOKEN_BYTES = 32;
    private static final String ACTIVE = "ACTIVE";
    private static final String REVOKED = "REVOKED";

    private static final DefaultRedisScript<Long> CREATE_SCRIPT = new DefaultRedisScript<>(
            """
            if redis.call('EXISTS', KEYS[1]) == 1 or redis.call('EXISTS', KEYS[2]) == 1 then
              return 0
            end
            redis.call('SET', KEYS[1], 'ACTIVE', 'PX', ARGV[1])
            redis.call('SET', KEYS[2], ARGV[2], 'PX', ARGV[1])
            return 1
            """,
            Long.class
    );

    private static final DefaultRedisScript<String> ROTATE_SCRIPT = new DefaultRedisScript<>(
            """
            local old = redis.call('GET', KEYS[1])
            if old then
              local separator = string.find(old, '|')
              if not separator then
                return 'INVALID'
              end
              local family = string.sub(old, 1, separator - 1)
              local familyKey = ARGV[1] .. family
              if redis.call('GET', familyKey) ~= 'ACTIVE' then
                return 'REVOKED'
              end
              local ttl = redis.call('PTTL', KEYS[1])
              if ttl <= 0 then
                return 'INVALID'
              end
              redis.call('DEL', KEYS[1])
              redis.call('SET', KEYS[2], family, 'PX', ttl)
              redis.call('SET', KEYS[3], old, 'PX', ttl)
              return 'ROTATED\\n' .. old .. '\\n' .. tostring(ttl)
            end

            local usedFamily = redis.call('GET', KEYS[2])
            if usedFamily then
              local familyKey = ARGV[1] .. usedFamily
              local familyTtl = redis.call('PTTL', familyKey)
              local usedTtl = redis.call('PTTL', KEYS[2])
              local ttl = math.max(familyTtl, usedTtl)
              if ttl > 0 then
                redis.call('SET', familyKey, 'REVOKED', 'PX', ttl)
              end
              return 'REPLAYED'
            end
            return 'INVALID'
            """,
            String.class
    );

    private static final DefaultRedisScript<String> REVOKE_TOKEN_SCRIPT =
            new DefaultRedisScript<>(
                    """
                    local metadata = redis.call('GET', KEYS[1])
                    local family = nil
                    if metadata then
                      local separator = string.find(metadata, '|')
                      if separator then
                        family = string.sub(metadata, 1, separator - 1)
                      end
                    else
                      family = redis.call('GET', KEYS[2])
                    end
                    if not family then
                      return 'INVALID'
                    end

                    local familyKey = ARGV[1] .. family
                    local familyTtl = redis.call('PTTL', familyKey)
                    local tokenTtl = redis.call('PTTL', KEYS[1])
                    local usedTtl = redis.call('PTTL', KEYS[2])
                    local ttl = math.max(familyTtl, tokenTtl, usedTtl)
                    if ttl > 0 then
                      redis.call('SET', familyKey, 'REVOKED', 'PX', ttl)
                      redis.call('SET', KEYS[2], family, 'PX', ttl)
                    end
                    redis.call('DEL', KEYS[1])
                    return 'REVOKED'
                    """,
                    String.class
            );

    private static final DefaultRedisScript<Long> REVOKE_FAMILY_SCRIPT =
            new DefaultRedisScript<>(
                    """
                    local ttl = redis.call('PTTL', KEYS[1])
                    if ttl <= 0 then
                      return 0
                    end
                    redis.call('SET', KEYS[1], 'REVOKED', 'PX', ttl)
                    return 1
                    """,
                    Long.class
            );

    private final StringRedisTemplate redis;
    private final SecurityProperties properties;
    private final SecureRandom secureRandom;
    private final Clock clock;
    private final String familyKeyPrefix;
    private final String activeTokenKeyPrefix;
    private final String usedTokenKeyPrefix;

    public RedisRefreshTokenFamilyStore(
            StringRedisTemplate redis,
            SecurityProperties properties
    ) {
        this(redis, properties, new SecureRandom(), Clock.systemUTC());
    }

    RedisRefreshTokenFamilyStore(
            StringRedisTemplate redis,
            SecurityProperties properties,
            SecureRandom secureRandom,
            Clock clock
    ) {
        this.redis = redis;
        this.properties = properties;
        this.secureRandom = secureRandom;
        this.clock = clock;
        this.familyKeyPrefix = properties.redisKeyPrefix() + "refresh:family:";
        this.activeTokenKeyPrefix = properties.redisKeyPrefix() + "refresh:token:";
        this.usedTokenKeyPrefix = properties.redisKeyPrefix() + "refresh:used:";
    }

    public IssuedRefreshToken createFamily(String userId, long securityVersion) {
        Instant expiresAt = clock.instant().plus(properties.refreshTokenTtl());
        long ttlMillis = properties.refreshTokenTtl().toMillis();
        for (int attempt = 0; attempt < 3; attempt++) {
            String familyId = UUID.randomUUID().toString();
            String rawToken = generateToken();
            String metadata = encodeMetadata(familyId, userId, securityVersion, expiresAt);
            try {
                Long created = redis.execute(
                        CREATE_SCRIPT,
                        List.of(familyKey(familyId), activeTokenKey(rawToken)),
                        Long.toString(ttlMillis),
                        metadata
                );
                if (Long.valueOf(1L).equals(created)) {
                    return new IssuedRefreshToken(rawToken, familyId, expiresAt);
                }
            } catch (DataAccessException exception) {
                throw unavailable(exception);
            }
        }
        throw new IllegalStateException("Unable to allocate refresh token family");
    }

    public RefreshRotationResult rotate(String presentedToken) {
        requireToken(presentedToken);
        String replacementToken = generateToken();
        try {
            String result = redis.execute(
                    ROTATE_SCRIPT,
                    List.of(
                            activeTokenKey(presentedToken),
                            usedTokenKey(presentedToken),
                            activeTokenKey(replacementToken)
                    ),
                    familyKeyPrefix
            );
            if (result == null) {
                throw new SecurityStateUnavailableException("Refresh token state was unavailable");
            }
            if (result.startsWith("ROTATED\n")) {
                String[] parts = result.split("\\n", 3);
                RefreshMetadata metadata = decodeMetadata(parts[1]);
                return new RefreshRotationResult(
                        RefreshRotationStatus.ROTATED,
                        replacementToken,
                        metadata.familyId(),
                        metadata.userId(),
                        metadata.securityVersion(),
                        metadata.expiresAt()
                );
            }
            return switch (result) {
                case "REPLAYED" -> RefreshRotationResult.withStatus(
                        RefreshRotationStatus.REPLAYED
                );
                case "REVOKED" -> RefreshRotationResult.withStatus(
                        RefreshRotationStatus.REVOKED
                );
                default -> RefreshRotationResult.withStatus(RefreshRotationStatus.INVALID);
            };
        } catch (DataAccessException exception) {
            throw unavailable(exception);
        }
    }

    public boolean revokeByToken(String presentedToken) {
        requireToken(presentedToken);
        try {
            String result = redis.execute(
                    REVOKE_TOKEN_SCRIPT,
                    List.of(activeTokenKey(presentedToken), usedTokenKey(presentedToken)),
                    familyKeyPrefix
            );
            if (result == null) {
                throw new SecurityStateUnavailableException("Refresh token state was unavailable");
            }
            return REVOKED.equals(result);
        } catch (DataAccessException exception) {
            throw unavailable(exception);
        }
    }

    public boolean revokeFamily(String familyId) {
        if (familyId == null || familyId.isBlank()) {
            throw new IllegalArgumentException("familyId must not be blank");
        }
        try {
            Long revoked = redis.execute(
                    REVOKE_FAMILY_SCRIPT,
                    List.of(familyKey(familyId))
            );
            if (revoked == null) {
                throw new SecurityStateUnavailableException("Refresh token state was unavailable");
            }
            return Long.valueOf(1L).equals(revoked);
        } catch (DataAccessException exception) {
            throw unavailable(exception);
        }
    }

    public boolean isFamilyActive(String familyId) {
        if (familyId == null || familyId.isBlank()) {
            return false;
        }
        try {
            return ACTIVE.equals(redis.opsForValue().get(familyKey(familyId)));
        } catch (DataAccessException exception) {
            throw unavailable(exception);
        }
    }

    static String digestToken(String rawToken) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(rawToken.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    private String generateToken() {
        byte[] bytes = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private String familyKey(String familyId) {
        return familyKeyPrefix + familyId;
    }

    private String activeTokenKey(String rawToken) {
        return activeTokenKeyPrefix + digestToken(rawToken);
    }

    private String usedTokenKey(String rawToken) {
        return usedTokenKeyPrefix + digestToken(rawToken);
    }

    private static String encodeMetadata(
            String familyId,
            String userId,
            long securityVersion,
            Instant expiresAt
    ) {
        String encodedUser = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(userId.getBytes(StandardCharsets.UTF_8));
        return String.join(
                "|",
                familyId,
                encodedUser,
                Long.toString(securityVersion),
                Long.toString(expiresAt.toEpochMilli())
        );
    }

    private static RefreshMetadata decodeMetadata(String value) {
        String[] parts = value.split("\\|", 4);
        if (parts.length != 4) {
            throw new IllegalStateException("Stored refresh metadata is invalid");
        }
        try {
            String userId = new String(
                    Base64.getUrlDecoder().decode(parts[1]),
                    StandardCharsets.UTF_8
            );
            return new RefreshMetadata(
                    parts[0],
                    userId,
                    Long.parseLong(parts[2]),
                    Instant.ofEpochMilli(Long.parseLong(parts[3]))
            );
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("Stored refresh metadata is invalid", exception);
        }
    }

    private static void requireToken(String token) {
        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException("refresh token must not be blank");
        }
    }

    private static SecurityStateUnavailableException unavailable(DataAccessException exception) {
        return new SecurityStateUnavailableException(
                "Refresh token state was unavailable",
                exception
        );
    }

    private record RefreshMetadata(
            String familyId,
            String userId,
            long securityVersion,
            Instant expiresAt
    ) {
    }

    public record IssuedRefreshToken(String token, String familyId, Instant expiresAt) {
    }

    public record RefreshRotationResult(
            RefreshRotationStatus status,
            String token,
            String familyId,
            String userId,
            long securityVersion,
            Instant expiresAt
    ) {
        static RefreshRotationResult withStatus(RefreshRotationStatus status) {
            return new RefreshRotationResult(status, null, null, null, 0L, null);
        }
    }

    public enum RefreshRotationStatus {
        ROTATED,
        REPLAYED,
        REVOKED,
        INVALID
    }
}
