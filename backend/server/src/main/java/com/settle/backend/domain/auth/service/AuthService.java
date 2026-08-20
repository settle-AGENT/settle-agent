package com.settle.backend.domain.auth.service;

import com.settle.backend.domain.auth.dto.AuthResponse;
import com.settle.backend.domain.auth.dto.LoginRequest;
import com.settle.backend.domain.auth.dto.SignUpRequest;
import com.settle.backend.domain.auth.exception.EmailAlreadyExistsException;
import com.settle.backend.domain.auth.exception.InvalidCredentialsException;
import com.settle.backend.domain.member.entity.Member;
import com.settle.backend.domain.member.repository.MemberRepository;
import java.util.Locale;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {
    private final MemberRepository memberRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenService jwtTokenService;

    public AuthService(
            MemberRepository memberRepository,
            PasswordEncoder passwordEncoder,
            JwtTokenService jwtTokenService
    ) {
        this.memberRepository = memberRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtTokenService = jwtTokenService;
    }

    @Transactional
    public AuthResponse signUp(SignUpRequest request) {
        String email = normalizeEmail(request.email());
        if (memberRepository.existsByEmail(email)) {
            throw new EmailAlreadyExistsException();
        }
        Member member = memberRepository.save(new Member(email, passwordEncoder.encode(request.password())));
        return response(member);
    }

    @Transactional(readOnly = true)
    public AuthResponse login(LoginRequest request) {
        Member member = memberRepository.findByEmail(normalizeEmail(request.email()))
                .orElseThrow(InvalidCredentialsException::new);
        if (!passwordEncoder.matches(request.password(), member.getPasswordHash())) {
            throw new InvalidCredentialsException();
        }
        return response(member);
    }

    private AuthResponse response(Member member) {
        return new AuthResponse(
                member.getId(),
                jwtTokenService.issue(member.getId(), member.getEmail()),
                "Bearer"
        );
    }

    private String normalizeEmail(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
