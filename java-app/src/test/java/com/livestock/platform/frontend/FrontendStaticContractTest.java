package com.livestock.platform.frontend;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class FrontendStaticContractTest {

    @Test
    void frontendUsesOnlyTheJavaBusinessApiForAuthenticatedWorkflows() throws IOException {
        String script = resource("static/app.js");

        assertThat(script)
                .contains(
                        "/api/v1/auth/login",
                        "/api/v1/auth/refresh",
                        "/api/v1/auth/logout",
                        "/api/v1/conversations",
                        "/api/v1/tasks/",
                        "/api/v1/system/status",
                        "/api/v1/measurements/analyze",
                        "Idempotency-Key",
                        "contextVersion",
                        "sessionStorage"
                )
                .doesNotContain(
                        "fetch(\"/api/chat",
                        "fetch(\"/api/conversations",
                        "fetch(\"/api/tasks",
                        "/internal/v1/ai/measurements/analyze",
                        "X-Client-ID"
                );
    }

    @Test
    void frontendExposesLoginConversationAndEvidenceSurfaces() throws IOException {
        String index = resource("static/index.html");

        assertThat(index)
                .contains(
                        "id=\"login-form\"",
                        "id=\"conversation-list\"",
                        "id=\"message-form\"",
                        "id=\"detail-summary\"",
                        "Trace &amp; Evidence"
                );
    }

    @Test
    void frontendExposesReliableDocumentUploadWorkflow() throws IOException {
        String index = resource("static/index.html");
        String script = resource("static/app.js");

        assertThat(index)
                .contains(
                        "id=\"open-upload\"",
                        "id=\"upload-dialog\"",
                        "id=\"upload-form\"",
                        "id=\"knowledge-file\"",
                        "accept=\"application/pdf,text/plain,.pdf,.txt\"",
                        "id=\"upload-status\""
                );
        assertThat(script)
                .contains(
                        "handleDocumentUpload",
                        "body.append(\"file\", file)",
                        "api(\"/api/v1/documents\"",
                        "Idempotency-Key",
                        "DOCUMENT_INDEX",
                        "pollTask(task.id)",
                        "`/api/v1/documents/${encodeURIComponent(document.id)}`"
                );
    }

    @Test
    void frontendExposesAuthorizedMeasurementAnalysisWorkflow() throws IOException {
        String index = resource("static/index.html");
        String script = resource("static/app.js");

        assertThat(index)
                .contains(
                        "id=\"open-measurement\"",
                        "id=\"measurement-dialog\"",
                        "id=\"measurement-form\"",
                        "name=\"animalId\"",
                        "name=\"bodyHeightCm\"",
                        "name=\"bodyLengthCm\"",
                        "name=\"chestGirthCm\"",
                        "name=\"chestDepthCm\"",
                        "name=\"chestWidthCm\"",
                        "name=\"weightKg\"",
                        "name=\"confidence\"",
                        "id=\"measurement-status\"",
                        "id=\"measurement-result\"",
                        "id=\"measurement-outcome\"",
                        "id=\"measurement-evidence\"",
                        "id=\"measurement-report\""
                );
        assertThat(script)
                .contains(
                        "handleMeasurementAnalysis",
                        "renderMeasurementResult",
                        "api(\"/api/v1/measurements/analyze\"",
                        "uniqueId(\"web-measurement\")",
                        "analysis.outcome",
                        "LOW_CONFIDENCE",
                        "INSUFFICIENT_DATA",
                        "result.summary",
                        "result.evidence",
                        "result.recommendation",
                        "result.report"
                );
    }

    private String resource(String name) throws IOException {
        try (var input = getClass().getClassLoader().getResourceAsStream(name)) {
            assertThat(input).as("classpath resource %s", name).isNotNull();
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
