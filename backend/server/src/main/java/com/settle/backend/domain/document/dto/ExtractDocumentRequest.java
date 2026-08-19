package com.settle.backend.domain.document.dto;

import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record ExtractDocumentRequest(
        @NotNull UUID uploadId
) {
}
