package com.livestock.platform.audit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.livestock.platform.audit.api.AuditLogView;
import java.time.Instant;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AuditLogViewTest {

    private static final String BEARER_SECRET = "bearer-secret-value";
    private static final String JWT_SECRET =
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop";
    private static final String REFRESH_SECRET = "R".repeat(43);
    private static final String API_KEY_SECRET = "sk-project_1234567890_secret";
    private static final String PASSWORD_SECRET = "correct-horse-battery-staple";

    @Test
    void sanitizesLegacyOrBypassedValuesBeforeApiMapping() {
        AuditLog log = mock(AuditLog.class);
        when(log.getId()).thenReturn(1L);
        when(log.getActorId()).thenReturn(42L);
        when(log.getAction()).thenReturn("USER_LOGIN");
        when(log.getResourceType()).thenReturn("AUTH_SESSION");
        when(log.getResourceId()).thenReturn(REFRESH_SECRET);
        when(log.getRequestId()).thenReturn(JWT_SECRET);
        when(log.getResult()).thenReturn("FAILURE");
        when(log.getClientIp()).thenReturn("apiKey=" + API_KEY_SECRET);
        when(log.getUserAgent()).thenReturn("Bearer " + BEARER_SECRET);
        when(log.getDetails()).thenReturn(
                Map.of("note", "password=" + PASSWORD_SECRET)
        );
        when(log.getCreatedAt()).thenReturn(Instant.EPOCH);

        AuditLogView view = AuditLogView.from(log, new AuditSanitizer());

        String rendered = view.toString();
        assertThat(rendered)
                .contains(AuditSanitizer.REDACTED)
                .doesNotContain(BEARER_SECRET)
                .doesNotContain(JWT_SECRET)
                .doesNotContain(REFRESH_SECRET)
                .doesNotContain(API_KEY_SECRET)
                .doesNotContain(PASSWORD_SECRET);
    }
}
