package com.settle.backend.domain.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

public record AuthResponse(
        @Schema(description = "AI session_id로도 사용되는 회원 ID") UUID memberId,
        @Schema(description = "API 인증용 JWT access token") String accessToken,
        @Schema(description = "Authorization scheme", example = "Bearer") String tokenType
) {
}
