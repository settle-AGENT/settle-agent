package com.settle.backend.domain.profile.controller;

import com.settle.backend.common.auth.CurrentMemberId;
import com.settle.backend.domain.profile.dto.ProfileConfirmRequest;
import com.settle.backend.domain.profile.service.ProfileService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
@Tag(
        name = "AI 프로필 연동",
        description = "OCR 결과에서 사용자가 수정한 프로필을 Spring을 통해 AI Agent에 전달합니다."
)
@SecurityRequirement(name = "bearerAuth")
public class ProfileController {
    private final ProfileService profileService;

    public ProfileController(ProfileService profileService) {
        this.profileService = profileService;
    }

    @PostMapping("/confirm")
    @Operation(
            summary = "OCR 프로필 확정",
            description = """
                    `message`는 JSON 객체가 아니라, **수정된 필드만 담은 JSON 문자열**입니다.
                    수정이 없으면 `"{}"`를 보내고 `editable=false` 필드는 절대 포함하지 않습니다.
                    `session_id`는 JWT memberId와 같아야 합니다.

                    Spring→AI: `${AI_BASE_URL}/api/profile/confirm`으로 같은 JSON을 전달하며,
                    AI의 HTTP status와 AgentResponse/error body를 그대로 반환합니다.
                    """
    )
    @ApiResponses({
            @ApiResponse(
                    responseCode = "200",
                    description = "프로필 확정 성공 — 갱신된 AgentResponse",
                    content = @Content(
                            mediaType = "application/json",
                            schema = @Schema(type = "object"),
                            examples = @ExampleObject(value = """
                                    {
                                      "schema_version": "1",
                                      "reply": "프로필을 확인했습니다. 다음 질문입니다.",
                                      "ui": {
                                        "type": "question",
                                        "payload": {
                                          "field": "phone_kr",
                                          "label": "본인 명의 국내 휴대폰이 있나요?",
                                          "input_type": "select",
                                          "options": [
                                            {"value": "yes", "label": "네"},
                                            {"value": "no", "label": "아니오"}
                                          ],
                                          "hint": null
                                        }
                                      },
                                      "state": {
                                        "session_id": "8c83fcab-0f4b-4ce6-9f2d-c9df3cfe6e11",
                                        "locale": "ko",
                                        "profile": {"nationality": "VNM"},
                                        "tasks": [],
                                        "documents": [],
                                        "pending_approval": null
                                      }
                                    }
                                    """)
                    )
            ),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "403", description = "session_id가 JWT memberId와 불일치",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"session_access_denied","message":"접근할 수 없는 상담 세션이에요.","details":null}}
                            """))),
            @ApiResponse(
                    responseCode = "422",
                    description = "message JSON 문자열 검증 실패",
                    content = @Content(
                            mediaType = "application/json",
                            examples = @ExampleObject(value = """
                                    {
                                      "detail": {
                                        "error": "validation_failed",
                                        "message": "message는 수정된 필드만 담은 JSON 객체 문자열이어야 합니다.",
                                        "details": [
                                          {"field": "message", "reason": "invalid_json_object_string"}
                                        ]
                                      }
                                    }
                                    """)
                    )
            ),
            @ApiResponse(responseCode = "5XX", description = "AI upstream 5xx는 같은 status/body로 전달")
    })
    public ResponseEntity<Map<String, Object>> confirm(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Valid @RequestBody ProfileConfirmRequest request
    ) {
        return profileService.confirm(memberId, request);
    }
}
