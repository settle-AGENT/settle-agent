package com.settle.backend.common.auth;

import java.util.UUID;

/**
 * AI 세션은 회원당 하나이며 session_id는 항상 memberId와 같습니다.
 * 다른 회원의 session_id로 접근하는 요청을 403으로 차단합니다.
 */
public final class SessionOwnership {

    private SessionOwnership() {
    }

    public static void require(UUID memberId, String sessionId) {
        if (memberId == null || !memberId.toString().equals(sessionId)) {
            throw new SessionAccessDeniedException();
        }
    }
}
