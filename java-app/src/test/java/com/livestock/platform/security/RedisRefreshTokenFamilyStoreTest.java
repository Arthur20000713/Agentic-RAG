package com.livestock.platform.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers(disabledWithoutDocker = true)
class RedisRefreshTokenFamilyStoreTest {

    private static final Instant NOW = Instant.parse("2026-07-30T00:00:00Z");

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    private LettuceConnectionFactory connectionFactory;
    private StringRedisTemplate redis;
    private RedisRefreshTokenFamilyStore store;

    @BeforeEach
    void setUp() {
        RedisStandaloneConfiguration configuration = new RedisStandaloneConfiguration(
                REDIS.getHost(),
                REDIS.getMappedPort(6379)
        );
        connectionFactory = new LettuceConnectionFactory(configuration);
        connectionFactory.afterPropertiesSet();
        connectionFactory.start();
        redis = new StringRedisTemplate(connectionFactory);
        redis.afterPropertiesSet();
        flushRedis();
        store = new RedisRefreshTokenFamilyStore(
                redis,
                properties(),
                new java.security.SecureRandom(),
                Clock.fixed(NOW, ZoneOffset.UTC)
        );
    }

    @AfterEach
    void tearDown() {
        if (connectionFactory != null) {
            connectionFactory.destroy();
        }
    }

    @Test
    void storesOnlyDigestAndPreservesAbsoluteTtlAcrossRotation() {
        var issued = store.createFamily("user-123", 4L);

        Set<String> keys = redis.keys("test:auth:*");
        assertThat(keys).isNotNull().hasSize(2);
        assertThat(keys).noneMatch(key -> key.contains(issued.token()));
        assertThat(issued.token()).hasSizeGreaterThanOrEqualTo(43);
        assertThat(store.isFamilyActive(issued.familyId())).isTrue();

        var rotated = store.rotate(issued.token());

        assertThat(rotated.status())
                .isEqualTo(RedisRefreshTokenFamilyStore.RefreshRotationStatus.ROTATED);
        assertThat(rotated.token()).isNotBlank().isNotEqualTo(issued.token());
        assertThat(rotated.familyId()).isEqualTo(issued.familyId());
        assertThat(rotated.userId()).isEqualTo("user-123");
        assertThat(rotated.securityVersion()).isEqualTo(4L);
        assertThat(rotated.expiresAt()).isEqualTo(issued.expiresAt());
        assertThat(redis.getExpire(activeTokenKey(rotated.token())))
                .isPositive()
                .isLessThanOrEqualTo(Duration.ofMinutes(10).toSeconds());
    }

    @Test
    void replayRevokesEntireFamilyIncludingSuccessor() {
        var issued = store.createFamily("user-123", 4L);
        var rotated = store.rotate(issued.token());

        var replay = store.rotate(issued.token());

        assertThat(replay.status())
                .isEqualTo(RedisRefreshTokenFamilyStore.RefreshRotationStatus.REPLAYED);
        assertThat(store.isFamilyActive(issued.familyId())).isFalse();
        assertThat(store.rotate(rotated.token()).status())
                .isEqualTo(RedisRefreshTokenFamilyStore.RefreshRotationStatus.REVOKED);
    }

    @Test
    void concurrentRefreshAllowsOneRotationAndTreatsTheOtherAsReplay() throws Exception {
        var issued = store.createFamily("user-123", 4L);
        var executor = Executors.newFixedThreadPool(2);
        try {
            Callable<RedisRefreshTokenFamilyStore.RefreshRotationResult> refresh =
                    () -> store.rotate(issued.token());
            var results = executor.invokeAll(List.of(refresh, refresh)).stream()
                    .map(future -> {
                        try {
                            return future.get();
                        } catch (Exception exception) {
                            throw new AssertionError(exception);
                        }
                    })
                    .toList();

            assertThat(results)
                    .extracting(RedisRefreshTokenFamilyStore.RefreshRotationResult::status)
                    .containsExactlyInAnyOrder(
                            RedisRefreshTokenFamilyStore.RefreshRotationStatus.ROTATED,
                            RedisRefreshTokenFamilyStore.RefreshRotationStatus.REPLAYED
                    );
            assertThat(store.isFamilyActive(issued.familyId())).isFalse();
            String successor = results.stream()
                    .filter(result -> result.status()
                            == RedisRefreshTokenFamilyStore.RefreshRotationStatus.ROTATED)
                    .findFirst()
                    .orElseThrow()
                    .token();
            assertThat(store.rotate(successor).status())
                    .isEqualTo(RedisRefreshTokenFamilyStore.RefreshRotationStatus.REVOKED);
        } finally {
            executor.shutdownNow();
        }
    }

    @Test
    void revokeByTokenInvalidatesAccessSessionAndRefreshToken() {
        var issued = store.createFamily("user-123", 4L);

        assertThat(store.revokeByToken(issued.token())).isTrue();
        assertThat(store.isFamilyActive(issued.familyId())).isFalse();
        assertThat(store.rotate(issued.token()).status())
                .isEqualTo(RedisRefreshTokenFamilyStore.RefreshRotationStatus.REPLAYED);
    }

    @Test
    void unknownRefreshTokenDoesNotCreateState() {
        assertThat(store.rotate("unknown-refresh-token").status())
                .isEqualTo(RedisRefreshTokenFamilyStore.RefreshRotationStatus.INVALID);
        assertThat(store.revokeByToken("unknown-refresh-token")).isFalse();
        assertThat(redis.keys("test:auth:*")).isEmpty();
    }

    @Test
    void redisFailureIsFailClosed() {
        StringRedisTemplate unavailableRedis = mock(StringRedisTemplate.class);
        when(unavailableRedis.opsForValue()).thenThrow(
                new RedisConnectionFailureException("offline")
        );
        RedisRefreshTokenFamilyStore unavailableStore =
                new RedisRefreshTokenFamilyStore(unavailableRedis, properties());

        assertThatThrownBy(() -> unavailableStore.isFamilyActive("family-123"))
                .isInstanceOf(SecurityStateUnavailableException.class)
                .hasMessageContaining("unavailable");
    }

    private void flushRedis() {
        try (RedisConnection connection = connectionFactory.getConnection()) {
            connection.serverCommands().flushDb();
        }
    }

    private static String activeTokenKey(String token) {
        return "test:auth:refresh:token:"
                + RedisRefreshTokenFamilyStore.digestToken(token);
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
