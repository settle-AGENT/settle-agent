package com.settle.backend.domain.auth.controller;

import com.settle.backend.domain.auth.dto.AuthResponse;
import com.settle.backend.domain.auth.dto.LoginRequest;
import com.settle.backend.domain.auth.dto.SignUpRequest;
import com.settle.backend.domain.auth.service.AuthService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
@Tag(name = "인증", description = "회원가입과 JWT access token 발급 API")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/signup")
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "회원가입", description = "이메일과 영문·숫자·특수문자를 포함한 8~64자 비밀번호로 가입하고 JWT를 발급합니다.")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "회원가입 및 JWT 발급 성공"),
            @ApiResponse(responseCode = "409", description = "이미 가입된 이메일",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"EMAIL_ALREADY_EXISTS","message":"이미 가입된 이메일이에요. 로그인하거나 다른 이메일을 사용해 주세요.","details":null}}
                            """))),
            @ApiResponse(responseCode = "422", description = "이메일, 비밀번호 또는 비밀번호 확인 검증 실패")
    })
    public AuthResponse signUp(@Valid @RequestBody SignUpRequest request) {
        return authService.signUp(request);
    }

    @PostMapping("/login")
    @Operation(summary = "로그인", description = "이메일·비밀번호·4자리 passcode를 검증하고 JWT를 발급합니다.")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "로그인 및 JWT 발급 성공"),
            @ApiResponse(responseCode = "401", description = "인증 정보 불일치",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"INVALID_CREDENTIALS","message":"이메일, 비밀번호 또는 패스코드를 확인해 주세요.","details":null}}
                            """))),
            @ApiResponse(responseCode = "422", description = "이메일, 비밀번호 또는 4자리 passcode 검증 실패")
    })
    public AuthResponse login(@Valid @RequestBody LoginRequest request) {
        return authService.login(request);
    }
}
