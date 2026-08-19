package com.settle.backend.domain.document.entity;

import com.settle.backend.domain.file.entity.DocumentType;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

public record IdentityDocument(
        UUID id,
        UUID memberId,
        DocumentType documentType,
        String objectKey,
        Map<String, Object> extractedData,
        Instant createdAt
) {
}
