package com.livestock.platform.ai.context;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.script.RedisScript;

class RedisAiContextStoreTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private StringRedisTemplate redis;
    private ValueOperations<String, String> values;
    private AiContextProperties properties;
    private RedisAiContextStore store;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        redis = org.mockito.Mockito.mock(StringRedisTemplate.class);
        values = org.mockito.Mockito.mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(values);
        properties = new AiContextProperties();
        store = new RedisAiContextStore(redis, objectMapper, properties);
    }

    @Test
    void defaultsMatchTheContextCacheContract() {
        assertThat(properties.keyPrefix()).isEqualTo("java:ai-context:");
        assertThat(properties.ttl()).isEqualTo(Duration.ofHours(24));
        assertThat(properties.maxBytes()).isEqualTo(65_536);
    }

    @Test
    void returnsOpaqueObjectOnlyWhenVersionMatchesExactly() throws Exception {
        JsonNode context = objectMapper.readTree(
                """
                {
                  "schemaVersion": 1,
                  "slots": {"animal": "cow", "nested": {"unknown": true}},
                  "providerExtension": ["opaque", 7]
                }
                """
        );
        String serialized = objectMapper.writeValueAsString(new AiContextEnvelope(4L, context));
        when(values.get("java:ai-context:12:34")).thenReturn(serialized);

        assertThat(store.get(12L, 34L, 4L)).contains(context);
        assertThat(store.get(12L, 34L, 3L)).isEmpty();
        assertThat(store.get(12L, 34L, 5L)).isEmpty();
        assertThat(store.get(12L, 34L, -1L)).isEmpty();
    }

    @Test
    void missingMalformedOversizedAndInvalidContextsAreCacheMisses() throws Exception {
        when(values.get(anyString()))
                .thenReturn(null)
                .thenReturn("{not-json")
                .thenReturn("x".repeat(65_537))
                .thenReturn(envelope(1L, "[]"))
                .thenReturn(envelope(1L, "{\"slots\":{}}"))
                .thenReturn(envelope(1L, "{\"schemaVersion\":0}"))
                .thenReturn(envelope(1L, "{\"schemaVersion\":1.5}"));

        for (int attempt = 0; attempt < 7; attempt++) {
            assertThat(store.get(1L, 2L, 1L)).isEmpty();
        }
    }

    @Test
    void redisReadFailureIsACacheMiss() {
        when(values.get(anyString()))
                .thenThrow(new RedisConnectionFailureException("offline"));

        assertThat(store.get(1L, 2L, 1L)).isEmpty();
    }

    @Test
    void writesEnvelopeWithConfiguredKeyAndTtl() throws Exception {
        properties.setKeyPrefix("test:context:");
        properties.setTtl(Duration.ofMinutes(30));
        JsonNode context = objectMapper.readTree(
                "{\"schemaVersion\":2,\"slots\":{\"symptom\":\"cough\"}}"
        );

        store.put(7L, 9L, 6L, context);

        ArgumentCaptor<Object> payload = ArgumentCaptor.forClass(Object.class);
        verify(redis).execute(
                any(RedisScript.class),
                eq(java.util.List.of("test:context:7:9")),
                eq("6"),
                payload.capture(),
                eq(String.valueOf(Duration.ofMinutes(30).toMillis()))
        );
        AiContextEnvelope envelope =
                objectMapper.readValue(payload.getValue().toString(), AiContextEnvelope.class);
        assertThat(envelope.contextVersion()).isEqualTo(6L);
        assertThat(envelope.context()).isEqualTo(context);
    }

    @Test
    void invalidOrOversizedWritesAreIgnored() throws Exception {
        properties.setMaxBytes(80);

        store.put(1L, 2L, 1L, objectMapper.readTree("[]"));
        store.put(1L, 2L, -1L, objectMapper.readTree("{\"schemaVersion\":1}"));
        store.put(1L, 2L, 1L, objectMapper.readTree("{\"schemaVersion\":0}"));
        store.put(
                1L,
                2L,
                1L,
                objectMapper.readTree(
                        "{\"schemaVersion\":1,\"slots\":\"" + "x".repeat(100) + "\"}"
                )
        );

        verify(redis, never()).execute(
                any(RedisScript.class),
                anyList(),
                any(Object[].class)
        );
    }

    @Test
    void redisWriteAndDeleteFailuresAreBestEffort() throws Exception {
        JsonNode context = objectMapper.readTree("{\"schemaVersion\":1}");
        org.mockito.Mockito.doThrow(new RedisConnectionFailureException("write offline"))
                .when(redis)
                .execute(any(RedisScript.class), anyList(), any(Object[].class));
        org.mockito.Mockito.doThrow(new RedisConnectionFailureException("delete offline"))
                .when(redis)
                .delete(anyString());

        assertThatCode(() -> store.put(3L, 4L, 2L, context)).doesNotThrowAnyException();
        assertThatCode(() -> store.delete(3L, 4L)).doesNotThrowAnyException();
        verify(redis).delete("java:ai-context:3:4");
    }

    private String envelope(long version, String contextJson) throws Exception {
        return objectMapper.writeValueAsString(
                new AiContextEnvelope(version, objectMapper.readTree(contextJson))
        );
    }
}
