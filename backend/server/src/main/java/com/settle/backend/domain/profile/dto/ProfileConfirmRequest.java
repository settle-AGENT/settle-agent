package com.settle.backend.domain.profile.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record ProfileConfirmRequest(
        @Schema(description = "JWT memberId와 같은 AI Agent 세션 ID", example = "8c83fcab-0f4b-4ce6-9f2d-c9df3cfe6e11")
        @JsonProperty("session_id") @NotBlank String sessionId,
        @Schema(
                description = "수정된 editable 필드만 담은 JSON 객체 문자열. 수정이 없으면 {}",
                example = "{\"nationality\":\"VNM\",\"addr_kr\":\"서울특별시 동작구 상도로 369\"}"
        )
        @NotNull String message
) {
}
