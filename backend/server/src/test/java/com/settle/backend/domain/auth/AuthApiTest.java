package com.settle.backend.domain.auth;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.settle.backend.domain.member.repository.MemberRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AuthApiTest {
    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private MemberRepository memberRepository;

    @BeforeEach
    void clearMembers() {
        memberRepository.deleteAll();
    }

    @Test
    void signsUpAndLogsInWithEmailPasswordAndGlobalPasscode() throws Exception {
        mockMvc.perform(post("/api/v1/auth/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "email": "User@Example.com",
                                  "password": "Password123!",
                                  "passwordConfirm": "Password123!"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.memberId").isString())
                .andExpect(jsonPath("$.accessToken").isString())
                .andExpect(jsonPath("$.tokenType").value("Bearer"));

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "email": "user@example.com",
                                  "password": "Password123!",
                                  "passcode": "1234"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accessToken").isString());
    }

    @Test
    void rejectsWrongPasscodeWithoutRevealingWhichCredentialFailed() throws Exception {
        mockMvc.perform(post("/api/v1/auth/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"email":"user@example.com","password":"Password123!","passwordConfirm":"Password123!"}
                        """));

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"user@example.com","password":"Password123!","passcode":"9999"}
                                """))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail.error").value("INVALID_CREDENTIALS"));
    }

    @Test
    void rejectsEmailOutsideSupportedFormat() throws Exception {
        mockMvc.perform(post("/api/v1/auth/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "email": "ㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁㅁ@a.a",
                                  "password": "Password123!",
                                  "passwordConfirm": "Password123!"
                                }
                                """))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.detail.error").value("validation_failed"))
                .andExpect(jsonPath("$.detail.details[*].field", hasItem("email")));
    }

    @Test
    void rejectsPasswordWithoutRequiredComplexity() throws Exception {
        mockMvc.perform(post("/api/v1/auth/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "email": "user@example.com",
                                  "password": "111111111111111111111111",
                                  "passwordConfirm": "111111111111111111111111"
                                }
                                """))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.detail.error").value("validation_failed"))
                .andExpect(jsonPath("$.detail.details[*].field", hasItem("password")));
    }

    @Test
    void rejectsPasswordLongerThanMaximum() throws Exception {
        String longPassword = "A1!" + "a".repeat(62);

        mockMvc.perform(post("/api/v1/auth/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"email":"user@example.com","password":"%s","passwordConfirm":"%s"}
                                """.formatted(longPassword, longPassword)))
                .andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.detail.error").value("validation_failed"))
                .andExpect(jsonPath("$.detail.details[*].field", hasItem("password")));
    }

    @Test
    void explainsWhenEmailIsAlreadyRegistered() throws Exception {
        String request = """
                {"email":"user@example.com","password":"Password123!","passwordConfirm":"Password123!"}
                """;

        mockMvc.perform(post("/api/v1/auth/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(request))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/api/v1/auth/signup")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(request))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.detail.error").value("EMAIL_ALREADY_EXISTS"))
                .andExpect(jsonPath("$.detail.message").value(
                        "이미 가입된 이메일이에요. 로그인하거나 다른 이메일을 사용해 주세요."
                ));
    }
}
