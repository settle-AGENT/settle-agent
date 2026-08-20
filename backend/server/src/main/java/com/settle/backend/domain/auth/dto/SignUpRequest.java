package com.settle.backend.domain.auth.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.Objects;

public record SignUpRequest(
        @Schema(example = "user@example.com", maxLength = 254)
        @NotBlank(message = "이메일을 입력해 주세요.")
        @Size(max = 254, message = "이메일은 254자 이하여야 합니다.")
        @Email(
                regexp = "^(?=.{1,64}@)[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\\.[A-Za-z]{2,63})+$",
                message = "올바른 이메일 주소를 입력해 주세요."
        )
        String email,
        @Schema(minLength = 8, maxLength = 64, format = "password")
        @NotBlank(message = "비밀번호를 입력해 주세요.")
        @Size(min = 8, max = 64, message = "비밀번호는 8~64자여야 합니다.")
        @Pattern(
                regexp = "^(?=.*[A-Za-z])(?=.*\\d)(?=.*[^A-Za-z0-9])[\\x21-\\x7E]+$",
                message = "비밀번호는 영문, 숫자, 특수문자만 사용하며 각각 1개 이상 포함해야 합니다."
        )
        String password,
        @Schema(minLength = 8, maxLength = 64, format = "password")
        @NotBlank(message = "비밀번호 확인을 입력해 주세요.")
        @Size(min = 8, max = 64, message = "비밀번호 확인은 8~64자여야 합니다.")
        String passwordConfirm
) {

    @AssertTrue(message = "비밀번호와 비밀번호 확인이 일치해야 합니다.")
    public boolean isPasswordConfirmed() {
        return Objects.equals(password, passwordConfirm);
    }
}
