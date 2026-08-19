package com.settle.backend.domain.document.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.UUID;

public record DocumentPreviewPayload(
        @JsonProperty("document_id") UUID documentId,
        String title,
        @JsonProperty("preview_url") String previewUrl,
        @JsonProperty("pdf_url") String pdfUrl,
        List<String> warnings
) {
    public DocumentPreviewPayload {
        warnings = List.copyOf(warnings == null ? List.of() : warnings);
    }
}
