package com.livestock.platform.common.web;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class RequestIdFilterTest {

    private final RequestIdFilter filter = new RequestIdFilter();

    @Test
    void propagatesValidRequestIdAndClearsMdc() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(RequestIds.HEADER_NAME, "req_client_0001");
        MockHttpServletResponse response = new MockHttpServletResponse();
        AtomicReference<String> requestIdInsideChain = new AtomicReference<>();
        FilterChain chain = (servletRequest, servletResponse) ->
                requestIdInsideChain.set(MDC.get(RequestIds.MDC_KEY));

        filter.doFilter(request, response, chain);

        assertThat(response.getHeader(RequestIds.HEADER_NAME)).isEqualTo("req_client_0001");
        assertThat(requestIdInsideChain.get()).isEqualTo("req_client_0001");
        assertThat(MDC.get(RequestIds.MDC_KEY)).isNull();
    }

    @Test
    void replacesMissingOrInvalidRequestId() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(RequestIds.HEADER_NAME, "bad id");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getHeader(RequestIds.HEADER_NAME))
                .matches("^req_[a-f0-9]{32}$");
        assertThat(MDC.get(RequestIds.MDC_KEY)).isNull();
    }
}
