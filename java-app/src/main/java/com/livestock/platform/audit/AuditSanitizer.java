package com.livestock.platform.audit;

import java.lang.reflect.Array;
import java.time.temporal.TemporalAccessor;
import java.util.ArrayList;
import java.util.Collection;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class AuditSanitizer {

    static final String REDACTED = "[REDACTED]";
    private static final String TRUNCATED = "[TRUNCATED]";
    private static final int MAX_DEPTH = 6;
    private static final int MAX_ENTRIES = 50;
    private static final int MAX_KEY_LENGTH = 128;
    private static final int MAX_VALUE_LENGTH = 512;
    private static final Pattern AUTHORIZATION_VALUE = Pattern.compile(
            "(?i)\\b(Bearer|Basic)\\s+[^\\s,;]+"
    );
    private static final Pattern JWT_VALUE = Pattern.compile(
            "(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}"
                    + "\\.[A-Za-z0-9_-]{8,}"
                    + "\\.[A-Za-z0-9_-]{8,}"
                    + "(?![A-Za-z0-9_-])"
    );
    private static final Pattern NAMED_SECRET_VALUE = Pattern.compile(
            "(?i)(\\b(?:password(?:hash)?|passwd|pwd|access[_-]?token"
                    + "|refresh[_-]?token|service[_-]?token|api[_-]?key"
                    + "|apikey|secret|jwt)\\b\\s*[\"']?\\s*[:=]\\s*[\"']?)"
                    + "([^\\s,;\"'&}]+)"
    );
    private static final Pattern PREFIXED_API_KEY = Pattern.compile(
            "(?i)(?<![A-Za-z0-9])(?:sk|rk)-[A-Za-z0-9_-]{12,}"
    );
    private static final Pattern REFRESH_TOKEN_VALUE = Pattern.compile(
            "(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"
    );
    private static final Set<String> SENSITIVE_KEYS = Set.of(
            "password",
            "passwordhash",
            "passwd",
            "pwd",
            "authorization",
            "accesstoken",
            "refreshtoken",
            "servicetoken",
            "token",
            "jwt",
            "apikey",
            "secret",
            "prompt",
            "content",
            "question",
            "answer"
    );

    public Map<String, Object> sanitize(Map<String, ?> details) {
        if (details == null || details.isEmpty()) {
            return Map.of();
        }
        IdentityHashMap<Object, Boolean> seen = new IdentityHashMap<>();
        return sanitizeMap(details, 0, seen);
    }

    private Map<String, Object> sanitizeMap(
            Map<?, ?> source,
            int depth,
            IdentityHashMap<Object, Boolean> seen
    ) {
        if (depth >= MAX_DEPTH || seen.put(source, Boolean.TRUE) != null) {
            return Map.of("_truncated", TRUNCATED);
        }
        try {
            Map<String, Object> sanitized = new LinkedHashMap<>();
            int count = 0;
            for (Map.Entry<?, ?> entry : source.entrySet()) {
                if (count++ >= MAX_ENTRIES) {
                    sanitized.put("_truncated", TRUNCATED);
                    break;
                }
                String originalKey = String.valueOf(entry.getKey());
                String key = truncate(sanitizeText(originalKey), MAX_KEY_LENGTH);
                sanitized.put(
                        key,
                        isSensitive(originalKey)
                                ? REDACTED
                                : sanitizeValue(entry.getValue(), depth + 1, seen)
                );
            }
            return sanitized;
        } finally {
            seen.remove(source);
        }
    }

    private Object sanitizeValue(
            Object value,
            int depth,
            IdentityHashMap<Object, Boolean> seen
    ) {
        if (value == null
                || value instanceof Boolean
                || value instanceof Number) {
            return value;
        }
        if (value instanceof CharSequence
                || value instanceof Character
                || value instanceof Enum<?>
                || value instanceof TemporalAccessor) {
            return sanitizeText(String.valueOf(value));
        }
        if (value instanceof Map<?, ?> map) {
            return sanitizeMap(map, depth, seen);
        }
        if (value instanceof Collection<?> collection) {
            return sanitizeCollection(collection, depth, seen);
        }
        if (value.getClass().isArray()) {
            return sanitizeArray(value, depth, seen);
        }
        return sanitizeText(String.valueOf(value));
    }

    private List<Object> sanitizeCollection(
            Collection<?> source,
            int depth,
            IdentityHashMap<Object, Boolean> seen
    ) {
        if (depth >= MAX_DEPTH || seen.put(source, Boolean.TRUE) != null) {
            return List.of(TRUNCATED);
        }
        try {
            List<Object> sanitized = new ArrayList<>();
            int count = 0;
            for (Object value : source) {
                if (count++ >= MAX_ENTRIES) {
                    sanitized.add(TRUNCATED);
                    break;
                }
                sanitized.add(sanitizeValue(value, depth + 1, seen));
            }
            return sanitized;
        } finally {
            seen.remove(source);
        }
    }

    private List<Object> sanitizeArray(
            Object source,
            int depth,
            IdentityHashMap<Object, Boolean> seen
    ) {
        if (depth >= MAX_DEPTH || seen.put(source, Boolean.TRUE) != null) {
            return List.of(TRUNCATED);
        }
        try {
            List<Object> sanitized = new ArrayList<>();
            int length = Math.min(Array.getLength(source), MAX_ENTRIES);
            for (int index = 0; index < length; index++) {
                sanitized.add(sanitizeValue(Array.get(source, index), depth + 1, seen));
            }
            if (Array.getLength(source) > MAX_ENTRIES) {
                sanitized.add(TRUNCATED);
            }
            return sanitized;
        } finally {
            seen.remove(source);
        }
    }

    private boolean isSensitive(String key) {
        String normalized = key.replaceAll("[^A-Za-z0-9]", "")
                .toLowerCase(Locale.ROOT);
        return SENSITIVE_KEYS.stream().anyMatch(normalized::contains);
    }

    public String sanitizeText(String value) {
        if (value == null) {
            return null;
        }
        String sanitized = replaceCredential(
                AUTHORIZATION_VALUE,
                value,
                "$1 " + REDACTED
        );
        sanitized = replaceCredential(JWT_VALUE, sanitized, REDACTED);
        sanitized = replaceCredential(
                NAMED_SECRET_VALUE,
                sanitized,
                "$1" + REDACTED
        );
        sanitized = replaceCredential(PREFIXED_API_KEY, sanitized, REDACTED);
        sanitized = replaceCredential(REFRESH_TOKEN_VALUE, sanitized, REDACTED);
        return truncate(sanitized, MAX_VALUE_LENGTH);
    }

    private String replaceCredential(Pattern pattern, String value, String replacement) {
        Matcher matcher = pattern.matcher(value);
        return matcher.replaceAll(replacement);
    }

    private String truncate(String value, int maximumLength) {
        if (value.length() <= maximumLength) {
            return value;
        }
        return value.substring(0, maximumLength - TRUNCATED.length()) + TRUNCATED;
    }
}
