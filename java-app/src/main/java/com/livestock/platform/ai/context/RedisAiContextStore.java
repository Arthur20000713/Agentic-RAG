package com.livestock.platform.ai.context;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public final class RedisAiContextStore {

    private static final Logger LOGGER =
            LoggerFactory.getLogger(RedisAiContextStore.class);
    private static final DefaultRedisScript<Long> PUT_IF_NEWER =
            new DefaultRedisScript<>(
                    """
                    local current = redis.call('GET', KEYS[1])
                    if current then
                        local ok, envelope = pcall(cjson.decode, current)
                        if ok and envelope and envelope.contextVersion
                                and tonumber(envelope.contextVersion) >= tonumber(ARGV[1]) then
                            return 0
                        end
                    end
                    redis.call('SET', KEYS[1], ARGV[2], 'PX', ARGV[3])
                    return 1
                    """,
                    Long.class
            );

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;
    private final AiContextProperties properties;

    public RedisAiContextStore(
            StringRedisTemplate redis,
            ObjectMapper objectMapper,
            AiContextProperties properties
    ) {
        this.redis = redis;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    public Optional<JsonNode> get(
            long userId,
            long conversationId,
            long expectedContextVersion
    ) {
        if (expectedContextVersion < 0) {
            return Optional.empty();
        }
        try {
            String serialized = redis.opsForValue().get(key(userId, conversationId));
            if (serialized == null || exceedsLimit(serialized)) {
                return Optional.empty();
            }
            AiContextEnvelope envelope =
                    objectMapper.readValue(serialized, AiContextEnvelope.class);
            if (envelope.contextVersion() != expectedContextVersion
                    || !isValidContext(envelope.context())) {
                return Optional.empty();
            }
            return Optional.of(envelope.context());
        } catch (JsonProcessingException | RuntimeException exception) {
            LOGGER.warn("AI context cache read failed; using bounded history");
            return Optional.empty();
        }
    }

    public void put(
            long userId,
            long conversationId,
            long contextVersion,
            JsonNode context
    ) {
        if (contextVersion < 0 || !isValidContext(context)) {
            return;
        }
        try {
            String serialized =
                    objectMapper.writeValueAsString(new AiContextEnvelope(contextVersion, context));
            if (exceedsLimit(serialized)) {
                return;
            }
            redis.execute(
                    PUT_IF_NEWER,
                    List.of(key(userId, conversationId)),
                    String.valueOf(contextVersion),
                    serialized,
                    String.valueOf(properties.ttl().toMillis())
            );
        } catch (JsonProcessingException | RuntimeException exception) {
            LOGGER.warn("AI context cache write failed; durable result is unchanged");
        }
    }

    public void delete(long userId, long conversationId) {
        try {
            redis.delete(key(userId, conversationId));
        } catch (RuntimeException exception) {
            LOGGER.warn("AI context cache delete failed; durable state is unchanged");
        }
    }

    private String key(long userId, long conversationId) {
        return properties.keyPrefix() + userId + ":" + conversationId;
    }

    private boolean exceedsLimit(String serialized) {
        return serialized.getBytes(StandardCharsets.UTF_8).length > properties.maxBytes();
    }

    private static boolean isValidContext(JsonNode context) {
        if (context == null || !context.isObject()) {
            return false;
        }
        JsonNode schemaVersion = context.get("schemaVersion");
        return schemaVersion != null
                && schemaVersion.isIntegralNumber()
                && schemaVersion.canConvertToLong()
                && schemaVersion.longValue() >= 1L;
    }
}
