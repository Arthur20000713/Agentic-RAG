package com.livestock.platform.ai;

import java.net.http.HttpClient;
import java.time.Duration;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class AiClientConfiguration {

    @Bean
    RestClient aiServiceRestClient(AiServiceProperties properties) {
        return restClient(properties, properties.readTimeout());
    }

    @Bean
    RestClient aiChatRestClient(AiServiceProperties properties) {
        return restClient(properties, properties.chatReadTimeout());
    }

    @Bean
    CircuitBreaker pythonAiChatCircuitBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .recordException(exception ->
                        exception instanceof AiChatClientException failure
                                && failure.circuitFailure()
                )
                .build();
        return CircuitBreaker.of("pythonAiChat", config);
    }

    @Bean
    Bulkhead pythonAiChatBulkhead(AiServiceProperties properties) {
        BulkheadConfig config = BulkheadConfig.custom()
                .maxConcurrentCalls(properties.chatMaxConcurrentCalls())
                .maxWaitDuration(Duration.ZERO)
                .build();
        return Bulkhead.of("pythonAiChat", config);
    }

    private static RestClient restClient(
            AiServiceProperties properties,
            Duration readTimeout
    ) {
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(properties.connectTimeout())
                .build();
        JdkClientHttpRequestFactory requestFactory =
                new JdkClientHttpRequestFactory(httpClient);
        requestFactory.setReadTimeout(readTimeout);
        return RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory)
                .build();
    }
}
