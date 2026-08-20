package com.settle.backend.domain.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record LoginRequest(
        @Schema(example = "user@example.com") @Email @NotBlank String email,
        @Schema(minLength = 8, maxLength = 128, format = "password")
        @NotBlank @Size(min = 8, max = 128) String password,
        @Schema(description = "숫자 4자리 전역 passcode", example = "1234", pattern = "\\d{4}")
        @NotBlank @Pattern(regexp = "\\d{4}", message = "패스코드는 숫자 4자리여야 합니다.") String passcode
) {
}
