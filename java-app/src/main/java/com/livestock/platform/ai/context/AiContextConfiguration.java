package com.livestock.platform.ai.context;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AiContextProperties.class)
class AiContextConfiguration {

    @Bean
    RedisAiContextStore redisAiContextStore(
            StringRedisTemplate redis,
            ObjectMapper objectMapper,
            AiContextProperties properties
    ) {
        return new RedisAiContextStore(redis, objectMapper, properties);
    }
}
