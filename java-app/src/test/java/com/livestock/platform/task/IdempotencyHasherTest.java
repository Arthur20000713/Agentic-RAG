package com.livestock.platform.task;

import static org.assertj.core.api.Assertions.assertThat;

import com.livestock.platform.task.domain.TaskType;
import com.livestock.platform.task.service.IdempotencyHasher;
import org.junit.jupiter.api.Test;

class IdempotencyHasherTest {

    private final IdempotencyHasher hasher = new IdempotencyHasher();

    @Test
    void sameCanonicalRequestHasTheSameHash() {
        assertThat(hasher.requestHash(42, TaskType.AI_QUERY, 3, "same content"))
                .isEqualTo("d8595d81e94dc1b97f4f60284696dcc4"
                        + "87fb01e4238c046230a8f064534c6250")
                .hasSize(64);
    }

    @Test
    void everyBusinessInputParticipatesInTheHash() {
        String baseline = hasher.requestHash(
                42,
                TaskType.AI_QUERY,
                3,
                "same content"
        );
        assertThat(hasher.requestHash(43, TaskType.AI_QUERY, 3, "same content"))
                .isNotEqualTo(baseline);
        assertThat(hasher.requestHash(42, TaskType.MEASUREMENT_ANALYSIS, 3, "same content"))
                .isNotEqualTo(baseline);
        assertThat(hasher.requestHash(42, TaskType.AI_QUERY, 4, "same content"))
                .isNotEqualTo(baseline);
        assertThat(hasher.requestHash(42, TaskType.AI_QUERY, 3, "different content"))
                .isNotEqualTo(baseline);
    }

    @Test
    void auditDigestDoesNotRevealTheRawIdempotencyKey() {
        String rawKey = "operation-secret-value";
        assertThat(hasher.keyDigest(rawKey))
                .hasSize(24)
                .doesNotContain(rawKey);
    }
}
