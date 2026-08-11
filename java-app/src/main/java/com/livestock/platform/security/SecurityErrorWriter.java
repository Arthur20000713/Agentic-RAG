package com.livestock.platform.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.livestock.platform.common.api.ApiErrorResponse;
import com.livestock.platform.common.web.RequestIds;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

@Component
public final class SecurityErrorWriter {

    private final ObjectMapper objectMapper;

    public SecurityErrorWriter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public void write(
            HttpServletResponse response,
            int status,
            String code,
            String message
    ) throws IOException {
        if (response.isCommitted()) {
            return;
        }
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        objectMapper.writeValue(
                response.getOutputStream(),
                ApiErrorResponse.of(RequestIds.current(), code, message)
        );
    }
}
