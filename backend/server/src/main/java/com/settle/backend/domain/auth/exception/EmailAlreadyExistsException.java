package com.settle.backend.domain.auth.exception;

public class EmailAlreadyExistsException extends RuntimeException {
    public EmailAlreadyExistsException() {
        super("이미 가입된 이메일이에요. 로그인하거나 다른 이메일을 사용해 주세요.");
    }
}
