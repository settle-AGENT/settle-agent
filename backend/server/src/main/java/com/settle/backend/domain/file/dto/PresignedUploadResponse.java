package com.settle.backend.domain.file.dto;

import java.util.UUID;

public record PresignedUploadResponse(
        UUID uploadId,
        String uploadUrl,
        long expiresInSeconds
) {
}
