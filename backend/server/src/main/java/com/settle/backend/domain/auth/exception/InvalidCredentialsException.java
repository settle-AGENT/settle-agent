package com.settle.backend.domain.auth.exception;

public class InvalidCredentialsException extends RuntimeException {
    public InvalidCredentialsException() {
        super("이메일 또는 비밀번호를 확인해 주세요.");
    }
}
