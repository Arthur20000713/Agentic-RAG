package com.livestock.platform.audit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.livestock.platform.audit.repository.AuditLogRepository;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class AuditServiceTest {

    private static final String BEARER_SECRET = "bearer-secret-value";
    private static final String JWT_SECRET =
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop";
    private static final String REFRESH_SECRET = "R".repeat(43);
    private static final String API_KEY_SECRET = "sk-project_1234567890_secret";
    private static final String PASSWORD_SECRET = "correct-horse-battery-staple";

    @Test
    void sanitizesEveryControllableStringBeforeAppend() {
        AuditLogRepository repository = mock(AuditLogRepository.class);
        when(repository.append(any(AuditLog.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
        AuditService service = new AuditService(repository, new AuditSanitizer());

        service.append(new AuditEvent(
                42L,
                "USER_LOGIN " + API_KEY_SECRET,
                "AUTH_SESSION Bearer " + BEARER_SECRET,
                REFRESH_SECRET,
                JWT_SECRET,
                "FAILURE password=" + PASSWORD_SECRET,
                "10.0.0.1 apiKey=" + API_KEY_SECRET,
                "Browser Bearer " + BEARER_SECRET + " " + "x".repeat(700),
                Map.of("note", "refreshToken=" + REFRESH_SECRET)
        ));

        ArgumentCaptor<AuditLog> captor = ArgumentCaptor.forClass(AuditLog.class);
        verify(repository).append(captor.capture());
        AuditLog stored = captor.getValue();
        String rendered = String.join(
                "|",
                stored.getAction(),
                stored.getResourceType(),
                stored.getResourceId(),
                stored.getRequestId(),
                stored.getResult(),
                stored.getClientIp(),
                stored.getUserAgent(),
                stored.getDetails().toString()
        );
        assertThat(rendered)
                .contains(AuditSanitizer.REDACTED)
                .doesNotContain(BEARER_SECRET)
                .doesNotContain(JWT_SECRET)
                .doesNotContain(REFRESH_SECRET)
                .doesNotContain(API_KEY_SECRET)
                .doesNotContain(PASSWORD_SECRET);
        assertThat(stored.getAction()).hasSizeLessThanOrEqualTo(64);
        assertThat(stored.getResourceType()).hasSizeLessThanOrEqualTo(64);
        assertThat(stored.getResourceId()).hasSizeLessThanOrEqualTo(128);
        assertThat(stored.getRequestId()).hasSizeLessThanOrEqualTo(128);
        assertThat(stored.getResult()).hasSizeLessThanOrEqualTo(16);
        assertThat(stored.getClientIp()).hasSizeLessThanOrEqualTo(45);
        assertThat(stored.getUserAgent()).hasSizeLessThanOrEqualTo(512);
    }
}
