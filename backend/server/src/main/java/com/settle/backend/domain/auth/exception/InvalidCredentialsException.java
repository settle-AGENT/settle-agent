package com.settle.backend.domain.auth.exception;

public class InvalidCredentialsException extends RuntimeException {
    public InvalidCredentialsException() {
        super("이메일, 비밀번호 또는 패스코드를 확인해 주세요.");
    }
}
