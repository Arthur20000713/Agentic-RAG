package com.livestock.platform.ai;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

public record AiChatRequest(
        String requestId,
        String operationId,
        String conversationId,
        String userId,
        String query,
        AnimalSnapshot animalSnapshot,
        List<HistoryItem> history,
        JsonNode context,
        long contextVersion,
        int deadlineMs
) {

    public AiChatRequest {
        history = List.copyOf(history);
    }

    public record AnimalSnapshot(
            String animalId,
            String species,
            String breed,
            String sex,
            LocalDate birthDate,
            Map<String, Object> attributes
    ) {

        public AnimalSnapshot {
            attributes = Map.copyOf(attributes);
        }
    }

    public record HistoryItem(
            String turnId,
            Role role,
            String content,
            Instant createdAt
    ) {
    }

    public enum Role {
        USER,
        ASSISTANT
    }
}
