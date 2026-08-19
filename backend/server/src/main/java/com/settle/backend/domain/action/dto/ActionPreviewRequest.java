package com.settle.backend.domain.action.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;

public record ActionPreviewRequest(
        @JsonProperty("session_id") @NotBlank String sessionId
) {
}
