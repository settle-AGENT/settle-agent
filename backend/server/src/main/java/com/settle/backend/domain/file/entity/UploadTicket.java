package com.settle.backend.domain.file.entity;

import java.time.Instant;
import java.util.UUID;

public record UploadTicket(
        UUID id,
        UUID memberId,
        DocumentType documentType,
        String objectKey,
        String contentType,
        UploadStatus status,
        Instant expiresAt
) {
    public UploadTicket withStatus(UploadStatus nextStatus) {
        return new UploadTicket(id, memberId, documentType, objectKey, contentType, nextStatus, expiresAt);
    }
}
