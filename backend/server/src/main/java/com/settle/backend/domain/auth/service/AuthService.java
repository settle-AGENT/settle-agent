package com.settle.backend.domain.auth.service;

import com.settle.backend.common.exception.FeatureNotConfiguredException;
import com.settle.backend.domain.auth.dto.AuthResponse;
import com.settle.backend.domain.auth.dto.LoginRequest;
import com.settle.backend.domain.auth.dto.SignUpRequest;
import org.springframework.stereotype.Service;

@Service
public class AuthService {

    public AuthResponse signUp(SignUpRequest request) {
        throw new FeatureNotConfiguredException("회원 저장소와 비밀번호/JWT 구현이 아직 연결되지 않았습니다.");
    }

    public AuthResponse login(LoginRequest request) {
        throw new FeatureNotConfiguredException("회원 저장소와 비밀번호/JWT 구현이 아직 연결되지 않았습니다.");
    }
}
