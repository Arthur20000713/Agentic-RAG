package com.livestock.platform.audit;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AuditSanitizerTest {

    private static final String BEARER_SECRET = "bearer-secret-value";
    private static final String JWT_SECRET =
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop";
    private static final String REFRESH_SECRET = "R".repeat(43);
    private static final String API_KEY_SECRET = "sk-project_1234567890_secret";
    private static final String PASSWORD_SECRET = "correct-horse-battery-staple";

    private final AuditSanitizer sanitizer = new AuditSanitizer();

    @Test
    void redactsSensitiveKeysAndCredentialsEmbeddedInOtherwiseSafeValues() {
        Map<String, Object> sanitized = sanitizer.sanitize(Map.of(
                "nestedPassword", PASSWORD_SECRET,
                "metadata", List.of(
                        "Bearer " + BEARER_SECRET,
                        JWT_SECRET,
                        REFRESH_SECRET,
                        API_KEY_SECRET,
                        "password=" + PASSWORD_SECRET
                ),
                "nested", Map.of(
                        "note", "refreshToken=" + REFRESH_SECRET,
                        "authorization", BEARER_SECRET
                )
        ));

        String rendered = sanitized.toString();
        assertThat(rendered)
                .contains(AuditSanitizer.REDACTED)
                .doesNotContain(BEARER_SECRET)
                .doesNotContain(JWT_SECRET)
                .doesNotContain(REFRESH_SECRET)
                .doesNotContain(API_KEY_SECRET)
                .doesNotContain(PASSWORD_SECRET);
    }

    @Test
    void sanitizesCredentialMaterialEmbeddedInMapKeys() {
        Map<String, Object> sanitized = sanitizer.sanitize(
                Map.of("password=" + PASSWORD_SECRET, "ordinary")
        );

        assertThat(sanitized.toString())
                .contains(AuditSanitizer.REDACTED)
                .doesNotContain(PASSWORD_SECRET);
    }

    @Test
    void keepsSanitizedTextBounded() {
        String sanitized = sanitizer.sanitizeText(
                "Bearer " + BEARER_SECRET + " " + "x".repeat(700)
        );

        assertThat(sanitized)
                .hasSize(512)
                .contains(AuditSanitizer.REDACTED)
                .doesNotContain(BEARER_SECRET);
    }
}
