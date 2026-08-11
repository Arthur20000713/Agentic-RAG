package com.livestock.platform.ai.context;

import com.fasterxml.jackson.databind.JsonNode;

public record AiContextEnvelope(long contextVersion, JsonNode context) {
}
