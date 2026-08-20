package com.settle.backend.domain.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.Objects;

public record SignUpRequest(
        @Schema(example = "user@example.com") @Email @NotBlank String email,
        @Schema(minLength = 8, maxLength = 128, format = "password")
        @NotBlank @Size(min = 8, max = 128) String password,
        @Schema(minLength = 8, maxLength = 128, format = "password")
        @NotBlank @Size(min = 8, max = 128) String passwordConfirm
) {

    @AssertTrue(message = "비밀번호와 비밀번호 확인이 일치해야 합니다.")
    public boolean isPasswordConfirmed() {
        return Objects.equals(password, passwordConfirm);
    }
}
