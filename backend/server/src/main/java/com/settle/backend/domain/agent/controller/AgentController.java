package com.settle.backend.domain.agent.controller;

import com.settle.backend.common.auth.CurrentMemberId;
import com.settle.backend.domain.agent.dto.AgentMessageRequest;
import com.settle.backend.domain.agent.dto.AgentSessionRequest;
import com.settle.backend.domain.agent.service.AgentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api")
@Tag(name = "AI 상담 및 과제", description = "화면 4~6의 질문, 과제 시작, 비교 응답을 중계합니다.")
@SecurityRequirement(name = "bearerAuth")
public class AgentController {
    private final AgentService agentService;

    public AgentController(AgentService agentService) {
        this.agentService = agentService;
    }

    @PostMapping("/session")
    @Operation(
            summary = "AI 세션 생성 또는 재개",
            description = "기본 세션을 재개하거나 fresh=true로 기존 작업과 분리된 새 상담 세션을 생성합니다."
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "AgentResponse 세션 상태",
                    content = @Content(examples = @ExampleObject(value = """
                            {"schema_version":"1","reply":"","ui":{"type":"none","payload":{}},"state":{"session_id":"8c83fcab-0f4b-4ce6-9f2d-c9df3cfe6e11","locale":"ko","profile":{},"tasks":[],"documents":[],"pending_approval":null}}
                            """))),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "5XX", description = "AI upstream 5xx는 같은 status/body로 전달")
    })
    public ResponseEntity<Map<String, Object>> createSession(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Parameter(description = "AI 응답 locale", example = "ko")
            @RequestParam(defaultValue = "ko") String locale,
            @RequestParam(defaultValue = "false") boolean reset,
            @RequestParam(defaultValue = "false") boolean fresh,
            @RequestParam(name = "session_id", required = false) String sessionId,
            @RequestParam(name = "source_session_id", required = false) String sourceSessionId
    ) {
        return agentService.createSession(
                memberId, locale, reset, fresh, sessionId, sourceSessionId
        );
    }

    @PostMapping("/chat")
    @Operation(
            summary = "AI 상담 답변 제출",
            description = "body.session_id는 JWT memberId와 같아야 합니다. AI status와 AgentResponse/error body를 그대로 반환합니다."
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "AgentResponse",
                    content = @Content(mediaType = "application/json", examples = @ExampleObject(value = """
                    {
                      "schema_version":"1",
                      "reply":"은행별 요건을 비교했습니다.",
                      "ui":{"type":"comparison","payload":{"title":"은행 비교","columns":["bank","requirement"],"rows":[{"bank":"A은행","requirement":"외국인등록증"}],"note":"개인 상황에 따라 달라질 수 있습니다.","as_of":"2026-08-19"}},
                      "state":{"session_id":"8c83fcab-0f4b-4ce6-9f2d-c9df3cfe6e11","tasks":[],"documents":[],"pending_approval":null}
                    }
                    """))),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "403", description = "session_id가 JWT memberId와 불일치",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"session_access_denied","message":"접근할 수 없는 상담 세션이에요.","details":null}}
                            """))),
            @ApiResponse(responseCode = "422", description = "요청 body 검증 실패"),
            @ApiResponse(responseCode = "5XX", description = "AI upstream 5xx는 같은 status/body로 전달")
    })
    public ResponseEntity<Map<String, Object>> chat(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Valid @RequestBody AgentMessageRequest request
    ) {
        return agentService.chat(memberId, request);
    }

    @PostMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter chatStream(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Valid @RequestBody AgentMessageRequest request
    ) {
        return agentService.chatStream(memberId, request);
    }

    @PostMapping("/actions/{id}/start")
    @Operation(
            summary = "과제 시작 또는 계속하기",
            description = "body.session_id는 JWT memberId와 같아야 합니다. locked 과제의 409 prerequisite_missing을 포함해 AI status/body를 그대로 반환합니다."
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "과제 시작 AgentResponse"),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "403", description = "session_id가 JWT memberId와 불일치"),
            @ApiResponse(responseCode = "409", description = "선행 과제 미완료",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"prerequisite_missing","message":"먼저 선행 과제를 완료해 주세요.","details":{"prereq":["verify_identity"]}}}
                            """))),
            @ApiResponse(responseCode = "422", description = "요청 body 또는 action id 검증 실패"),
            @ApiResponse(responseCode = "5XX", description = "AI upstream 5xx는 같은 status/body로 전달")
    })
    public ResponseEntity<Map<String, Object>> startAction(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Parameter(description = "과제 ID", example = "open_account")
            @PathVariable("id") @NotBlank String actionId,
            @Valid @RequestBody AgentSessionRequest request
    ) {
        return agentService.startAction(memberId, actionId, request);
    }
}
