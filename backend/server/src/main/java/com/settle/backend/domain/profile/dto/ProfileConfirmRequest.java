package com.settle.backend.domain.profile.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ProfileConfirmRequest(
        @JsonProperty("session_id") @NotBlank String sessionId,
        @NotNull String message
) {
}
