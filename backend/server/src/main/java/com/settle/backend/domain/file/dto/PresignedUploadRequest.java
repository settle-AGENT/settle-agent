package com.settle.backend.domain.file.dto;

import com.settle.backend.domain.file.entity.DocumentType;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

public record PresignedUploadRequest(
        @Schema(
                description = "AI와 합의한 문서 타입",
                allowableValues = {"arc_front", "arc_back", "passport"},
                example = "arc_front"
        )
        @NotNull DocumentType documentType
) {
}
