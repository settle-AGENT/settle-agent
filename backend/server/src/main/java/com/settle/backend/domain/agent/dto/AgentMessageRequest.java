package com.settle.backend.domain.agent.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;

public record AgentMessageRequest(
        @Schema(description = "JWT memberId와 같은 AI Agent 세션 ID", example = "8c83fcab-0f4b-4ce6-9f2d-c9df3cfe6e11")
        @JsonProperty("session_id") @NotBlank String sessionId,
        @Schema(description = "현재 질문에 대한 사용자 답변", example = "고려대학교")
        @NotBlank String message
) {
}
