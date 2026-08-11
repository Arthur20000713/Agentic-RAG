package com.livestock.platform.ai;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;

public record AiChatResponse(
        String requestId,
        String operationId,
        String runId,
        Outcome outcome,
        String answer,
        String intent,
        RiskLevel riskLevel,
        EvidenceStatus evidenceStatus,
        List<SourceCitation> sources,
        List<String> followUpQuestions,
        List<String> toolsUsed,
        SafetyDecision safety,
        JsonNode nextContext,
        long contextVersion,
        String traceId
) {

    public AiChatResponse {
        sources = List.copyOf(sources);
        followUpQuestions = List.copyOf(followUpQuestions);
        toolsUsed = List.copyOf(toolsUsed);
    }

    public enum Outcome {
        ANSWERED,
        NEEDS_FOLLOW_UP,
        LOW_CONFIDENCE,
        SAFETY_REFUSAL
    }

    public enum RiskLevel {
        LOW,
        MEDIUM,
        HIGH,
        CRITICAL
    }

    public enum EvidenceStatus {
        SUPPORTED,
        LOW_CONFIDENCE,
        EMPTY,
        UNAVAILABLE,
        NOT_REQUIRED
    }

    public record SourceCitation(
            String collection,
            JsonNode documentId,
            String title,
            String sourceUri,
            Integer page,
            String sectionTitle,
            String chunkId,
            double score
    ) {
    }

    public record SafetyDecision(
            Decision decision,
            String reasonCode
    ) {
    }

    public enum Decision {
        ALLOWED,
        REFUSED
    }
}
