package com.livestock.platform.system;

import com.livestock.platform.ai.PythonAiClient;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class SystemStatusService {

    private final JdbcTemplate jdbcTemplate;
    private final RedisConnectionFactory redisConnectionFactory;
    private final PythonAiClient pythonAiClient;

    public SystemStatusService(
            JdbcTemplate jdbcTemplate,
            RedisConnectionFactory redisConnectionFactory,
            PythonAiClient pythonAiClient
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.redisConnectionFactory = redisConnectionFactory;
        this.pythonAiClient = pythonAiClient;
    }

    public SystemStatusResponse status() {
        Map<String, DependencyStatus> dependencies = new LinkedHashMap<>();
        dependencies.put("mysql", check(this::verifyMysql));
        dependencies.put("redis", check(this::verifyRedis));
        dependencies.put("pythonAi", check(pythonAiClient::verifyConnection));
        return new SystemStatusResponse("livestock-business-service", dependencies);
    }

    private void verifyMysql() {
        jdbcTemplate.queryForObject("SELECT 1", Integer.class);
    }

    private void verifyRedis() {
        try (RedisConnection connection = redisConnectionFactory.getConnection()) {
            String pong = connection.ping();
            if (!"PONG".equalsIgnoreCase(pong)) {
                throw new IllegalStateException("Redis ping failed");
            }
        }
    }

    private DependencyStatus check(DependencyCheck dependencyCheck) {
        try {
            dependencyCheck.verify();
            return DependencyStatus.up();
        } catch (Exception exception) {
            return DependencyStatus.down();
        }
    }

    @FunctionalInterface
    private interface DependencyCheck {
        void verify();
    }
}
