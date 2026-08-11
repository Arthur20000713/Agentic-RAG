package com.livestock.platform.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class AiServicePropertiesTest {

    @Test
    void toStringRedactsServiceToken() {
        AiServiceProperties properties = new AiServiceProperties();
        properties.setBaseUrl("http://python-ai:8000");
        properties.setServiceToken("sensitive-service-token");

        assertThat(properties.toString())
                .contains("http://python-ai:8000")
                .contains("[REDACTED]")
                .doesNotContain("sensitive-service-token");
        assertThat(properties.recoveryLease()).isEqualTo(Duration.ofSeconds(90));
        assertThatThrownBy(() -> properties.setRecoveryLease(Duration.ofSeconds(60)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
