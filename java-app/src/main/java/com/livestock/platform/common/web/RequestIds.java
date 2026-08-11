package com.livestock.platform.common.web;

import java.util.Optional;
import org.slf4j.MDC;

public final class RequestIds {

    public static final String HEADER_NAME = "X-Request-ID";
    public static final String MDC_KEY = "requestId";

    private RequestIds() {
    }

    public static String current() {
        return Optional.ofNullable(MDC.get(MDC_KEY)).orElse("req_unavailable");
    }
}
