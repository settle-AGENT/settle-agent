package com.settle.backend.common.auth;

import java.util.UUID;

/** 회원의 기본 세션과 서버가 발급한 추가 상담 세션만 허용합니다. */
public final class SessionOwnership {

    private static final String SEPARATOR = "--";

    private SessionOwnership() {
    }

    public static void require(UUID memberId, String sessionId) {
        if (memberId == null || sessionId == null) {
            throw new SessionAccessDeniedException();
        }
        String owner = memberId.toString();
        if (!owner.equals(sessionId) && !sessionId.startsWith(owner + SEPARATOR)) {
            throw new SessionAccessDeniedException();
        }
    }

    public static String freshId(UUID memberId) {
        return memberId + SEPARATOR + UUID.randomUUID().toString().replace("-", "");
    }
}
