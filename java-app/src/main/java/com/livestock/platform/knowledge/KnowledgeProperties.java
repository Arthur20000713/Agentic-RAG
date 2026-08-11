package com.livestock.platform.knowledge;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.nio.file.Path;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "livestock.knowledge")
public class KnowledgeProperties {

    @NotBlank
    private String sharedRoot = "data/uploads";

    @NotBlank
    private String collection = "test";

    @Positive
    private long maxFileBytes = 104_857_600L;

    private Duration indexDeadline = Duration.ofMinutes(10);

    private long reconciliationDelayMillis = 1000L;

    private boolean reconciliationEnabled = true;

    public Path sharedRoot() {
        return Path.of(sharedRoot).toAbsolutePath().normalize();
    }

    public void setSharedRoot(String sharedRoot) {
        this.sharedRoot = sharedRoot;
    }

    public String collection() {
        return collection;
    }

    public void setCollection(String collection) {
        this.collection = collection;
    }

    public long maxFileBytes() {
        return maxFileBytes;
    }

    public void setMaxFileBytes(long maxFileBytes) {
        this.maxFileBytes = maxFileBytes;
    }

    public Duration indexDeadline() {
        return indexDeadline;
    }

    public void setIndexDeadline(Duration indexDeadline) {
        this.indexDeadline = indexDeadline;
    }

    public long reconciliationDelayMillis() {
        return reconciliationDelayMillis;
    }

    public void setReconciliationDelayMillis(long reconciliationDelayMillis) {
        this.reconciliationDelayMillis = reconciliationDelayMillis;
    }

    public boolean reconciliationEnabled() {
        return reconciliationEnabled;
    }

    public void setReconciliationEnabled(boolean reconciliationEnabled) {
        this.reconciliationEnabled = reconciliationEnabled;
    }
}
