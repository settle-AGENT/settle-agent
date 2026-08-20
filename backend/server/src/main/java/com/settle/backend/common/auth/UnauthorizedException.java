package com.settle.backend.common.auth;

/**
 * Bearer token이 없거나 무효할 때 발생합니다.
 * error 코드는 클라이언트 분기를 위해 고정하고, message는 사용자에게 그대로 노출됩니다.
 */
public class UnauthorizedException extends RuntimeException {
    public static final String ERROR_CODE = "invalid_or_missing_token";

    public UnauthorizedException() {
        super("로그인이 만료되었어요. 다시 로그인해 주세요.");
    }
}
