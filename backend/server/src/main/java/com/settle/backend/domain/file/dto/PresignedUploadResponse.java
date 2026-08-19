package com.settle.backend.domain.file.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

public record PresignedUploadResponse(
        @Schema(description = "후속 OCR 요청에 사용할 업로드 ID")
        UUID uploadId,
        @Schema(description = "S3 presigned PUT URL")
        String uploadUrl,
        @Schema(description = "URL 만료까지 남은 초", example = "300")
        long expiresInSeconds
) {
}
