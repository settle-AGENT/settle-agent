package com.settle.backend.domain.document.dto;

import com.settle.backend.domain.file.entity.DocumentType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record ExtractDocumentRequest(
        @NotNull DocumentType documentType,
        @NotBlank @Size(max = 1024) String objectKey
) {
}
