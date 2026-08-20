package com.settle.backend.domain.action.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

public record AgentResponse(
        @JsonProperty("schema_version") String schemaVersion,
        String reply,
        Ui ui,
        Map<String, Object> state
) {
    public record Ui(String type, Object payload) {
    }
}
