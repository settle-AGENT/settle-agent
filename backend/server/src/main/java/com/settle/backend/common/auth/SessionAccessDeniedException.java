package com.settle.backend.common.auth;

/**
 * 다른 회원의 session_id로 접근할 때 발생합니다.
 * error 코드는 클라이언트 분기를 위해 고정하고, message는 사용자에게 그대로 노출됩니다.
 */
public class SessionAccessDeniedException extends RuntimeException {
    public static final String ERROR_CODE = "session_access_denied";

    public SessionAccessDeniedException() {
        super("접근할 수 없는 상담 세션이에요.");
    }
}
