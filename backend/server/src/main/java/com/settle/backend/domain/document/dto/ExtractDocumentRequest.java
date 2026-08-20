package com.settle.backend.domain.document.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record ExtractDocumentRequest(
        @Schema(
                description = "`POST /api/v1/uploads`에서 발급받은 업로드 식별자",
                example = "8c83fcab-0f4b-4ce6-9f2d-c9df3cfe6e11"
        )
        @NotNull UUID uploadId,
        @JsonProperty("session_id") @NotBlank String sessionId
) {
}
