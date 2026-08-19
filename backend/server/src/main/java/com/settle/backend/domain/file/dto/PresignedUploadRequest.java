package com.settle.backend.domain.file.dto;

import com.settle.backend.domain.file.entity.DocumentType;
import jakarta.validation.constraints.NotNull;

public record PresignedUploadRequest(
        @NotNull DocumentType documentType
) {
}
