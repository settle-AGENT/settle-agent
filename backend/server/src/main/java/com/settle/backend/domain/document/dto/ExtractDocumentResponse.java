package com.settle.backend.domain.document.dto;

import com.settle.backend.domain.file.entity.DocumentType;
import java.util.Map;
import java.util.UUID;

public record ExtractDocumentResponse(
        UUID documentId,
        DocumentType documentType,
        String objectKey,
        Map<String, Object> extractedData
) {
}
