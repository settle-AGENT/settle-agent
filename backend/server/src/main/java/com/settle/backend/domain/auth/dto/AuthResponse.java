package com.settle.backend.domain.auth.dto;

import java.util.UUID;

public record AuthResponse(UUID memberId, String accessToken, String tokenType) {
}
