package com.livestock.platform.ai;

import com.livestock.platform.common.web.RequestIds;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PythonAiClient {

    private final RestClient restClient;
    private final AiServiceProperties properties;

    public PythonAiClient(RestClient aiServiceRestClient, AiServiceProperties properties) {
        this.restClient = aiServiceRestClient;
        this.properties = properties;
    }

    public void verifyConnection() {
        restClient.get()
                .uri("/internal/v1/rag/collections?includeStats=false")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + properties.serviceToken())
                .header(RequestIds.HEADER_NAME, requestId())
                .retrieve()
                .toBodilessEntity();
    }

    private String requestId() {
        String current = RequestIds.current();
        if (!"req_unavailable".equals(current)) {
            return current;
        }
        return "req_health_" + UUID.randomUUID().toString().replace("-", "");
    }
}
