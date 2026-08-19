package com.settle.backend.domain.file.dto;

public record PresignedUploadResponse(
        String objectKey,
        String uploadUrl,
        long expiresInSeconds
) {
}
