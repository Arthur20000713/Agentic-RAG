package com.livestock.platform.ai;

import java.net.http.HttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class MeasurementAiClientConfiguration {

    @Bean
    RestClient aiMeasurementRestClient(AiServiceProperties properties) {
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(properties.connectTimeout())
                .build();
        JdkClientHttpRequestFactory requestFactory =
                new JdkClientHttpRequestFactory(httpClient);
        requestFactory.setReadTimeout(properties.measurementReadTimeout());
        return RestClient.builder()
                .baseUrl(properties.baseUrl())
                .requestFactory(requestFactory)
                .build();
    }
}
