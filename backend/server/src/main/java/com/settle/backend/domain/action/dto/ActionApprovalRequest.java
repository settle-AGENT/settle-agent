package com.settle.backend.domain.action.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ActionApprovalRequest(
        @NotBlank @JsonProperty("session_id") String sessionId,
        @NotNull Boolean approved
) {
}
