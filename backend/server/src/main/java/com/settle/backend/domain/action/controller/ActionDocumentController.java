package com.settle.backend.domain.action.controller;

import com.settle.backend.common.auth.CurrentMemberId;
import com.settle.backend.domain.action.dto.ActionApprovalRequest;
import com.settle.backend.domain.action.dto.ActionPreviewRequest;
import com.settle.backend.domain.action.dto.AgentResponse;
import com.settle.backend.domain.action.service.ActionPreviewService;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Tag(
        name = "과제 실행 및 문서",
        description = "화면 7~9의 실행 미리보기, 승인, 실행 이력, 생성 문서 조회를 제공합니다."
)
@SecurityRequirement(name = "bearerAuth")
public class ActionDocumentController {

    private final ActionPreviewService actionPreviewService;
    private final GeneratedDocumentService documentService;

    public ActionDocumentController(
            ActionPreviewService actionPreviewService,
            GeneratedDocumentService documentService
    ) {
        this.actionPreviewService = actionPreviewService;
        this.documentService = documentService;
    }

    @PostMapping("/api/actions/{actionId}/preview")
    @Operation(
            summary = "과제 실행 미리보기",
            description = """
                    body.session_id는 JWT memberId와 같아야 합니다.
                    AI가 doc_preview를 반환하면 PDF를 내려받아 저장하고 payload의 URL을 \
                    백엔드 경로(/api/documents/{id}/preview, /download)로 교체합니다."""
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "AgentResponse",
                    content = @Content(examples = @ExampleObject(value = """
                            {"schema_version":"1","reply":"신청서를 준비했어요.","ui":{"type":"doc_preview","payload":{"document_id":"20000000-0000-0000-0000-000000000002","title":"계좌개설신청서","preview_url":"/api/documents/20000000-0000-0000-0000-000000000002/preview","pdf_url":"/api/documents/20000000-0000-0000-0000-000000000002/download","warnings":[]}},"state":{"documents":[]}}
                            """))),
            @ApiResponse(responseCode = "400", description = "AI doc_preview payload가 규약과 다름",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"INVALID_ARGUMENT","message":"invalid_ai_doc_preview","details":null}}
                            """))),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"invalid_or_missing_token","message":"로그인이 만료되었어요. 다시 로그인해 주세요.","details":null}}
                            """))),
            @ApiResponse(responseCode = "403", description = "session_id가 JWT memberId와 불일치",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"session_access_denied","message":"접근할 수 없는 상담 세션이에요.","details":null}}
                            """))),
            @ApiResponse(responseCode = "422", description = "요청 body 검증 실패"),
            @ApiResponse(responseCode = "5XX", description = "AI upstream 5xx는 같은 status/body로 전달")
    })
    public AgentResponse preview(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Parameter(description = "과제 ID", example = "open_bank_account")
            @PathVariable String actionId,
            @Valid @RequestBody ActionPreviewRequest request
    ) {
        return actionPreviewService.preview(memberId, actionId, request.sessionId());
    }

    @PostMapping("/api/actions/{actionId}/approve")
    @Operation(
            summary = "실행 승인 또는 취소",
            description = """
                    body.session_id는 JWT memberId와 같아야 합니다.
                    path의 actionId는 AI state의 pending_approval.action_id와 일치해야 합니다.
                    이미 ledger에 실행 기록이 있으면 재실행 없이 현재 상태를 반환합니다."""
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "승인 처리 후 AgentResponse"),
            @ApiResponse(responseCode = "400",
                    description = "pending_approval 없음(pending_approval_not_found), "
                            + "action 불일치(approval_action_mismatch), "
                            + "pending_approval 형식 오류(invalid_pending_approval)",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"INVALID_ARGUMENT","message":"approval_action_mismatch","details":null}}
                            """))),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "403", description = "session_id가 JWT memberId와 불일치",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"session_access_denied","message":"접근할 수 없는 상담 세션이에요.","details":null}}
                            """))),
            @ApiResponse(responseCode = "422", description = "요청 body 검증 실패"),
            @ApiResponse(responseCode = "5XX", description = "AI upstream 5xx는 같은 status/body로 전달")
    })
    public AgentResponse approve(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Parameter(description = "과제 ID", example = "open_bank_account")
            @PathVariable String actionId,
            @Valid @RequestBody ActionApprovalRequest request
    ) {
        return actionPreviewService.approve(
                memberId,
                actionId,
                request.sessionId(),
                request.approved()
        );
    }

    @GetMapping("/api/ledger")
    @Operation(
            summary = "실행 이력 조회",
            description = "session_id는 JWT memberId와 같아야 합니다. AI ledger를 그대로 반환합니다."
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "실행 이력 목록",
                    content = @Content(examples = @ExampleObject(value = """
                            [{"action":"open_bank_account","status":"executed","at":"2026-08-19T00:00:00Z"}]
                            """))),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "403", description = "session_id가 JWT memberId와 불일치",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"session_access_denied","message":"접근할 수 없는 상담 세션이에요.","details":null}}
                            """))),
            @ApiResponse(responseCode = "5XX", description = "AI upstream 5xx는 같은 status/body로 전달")
    })
    public List<Map<String, Object>> ledger(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Parameter(description = "JWT memberId와 같은 값", example = "10000000-0000-0000-0000-000000000001")
            @RequestParam("session_id") String sessionId
    ) {
        return actionPreviewService.ledger(memberId, sessionId);
    }

    @GetMapping("/api/documents/{documentId}/preview")
    @Operation(
            summary = "생성 문서 브라우저 열람",
            description = """
                    Content-Disposition: inline로 PDF를 반환합니다.
                    본인 소유이면서 status가 READY인 문서만 조회됩니다. \
                    타인 문서는 존재 여부를 노출하지 않기 위해 404로 응답합니다."""
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "PDF 바이너리",
                    content = @Content(mediaType = MediaType.APPLICATION_PDF_VALUE)),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "404", description = "문서 없음, 타인 문서, 또는 READY 아님",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"RESOURCE_NOT_FOUND","message":"문서를 찾을 수 없습니다: 20000000-0000-0000-0000-000000000002","details":null}}
                            """)))
    })
    public ResponseEntity<byte[]> viewDocument(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Parameter(description = "생성 문서 ID", example = "20000000-0000-0000-0000-000000000002")
            @PathVariable UUID documentId
    ) {
        return pdfResponse(memberId, documentId, false);
    }

    @GetMapping("/api/documents/{documentId}/download")
    @Operation(
            summary = "생성 문서 다운로드",
            description = """
                    Content-Disposition: attachment로 PDF를 반환합니다. 파일명은 문서 제목입니다.
                    본인 소유이면서 status가 READY인 문서만 조회됩니다. \
                    타인 문서는 존재 여부를 노출하지 않기 위해 404로 응답합니다."""
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "PDF 바이너리",
                    content = @Content(mediaType = MediaType.APPLICATION_PDF_VALUE)),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "404", description = "문서 없음, 타인 문서, 또는 READY 아님")
    })
    public ResponseEntity<byte[]> downloadDocument(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Parameter(description = "생성 문서 ID", example = "20000000-0000-0000-0000-000000000002")
            @PathVariable UUID documentId
    ) {
        return pdfResponse(memberId, documentId, true);
    }

    private ResponseEntity<byte[]> pdfResponse(UUID memberId, UUID documentId, boolean download) {
        GeneratedDocumentService.DocumentFile file = documentService.loadPdf(memberId, documentId);
        String fileName = file.title().replaceAll("[\\\\/\\r\\n]", "_") + ".pdf";
        ContentDisposition disposition = (download
                ? ContentDisposition.attachment()
                : ContentDisposition.inline())
                .filename(fileName, StandardCharsets.UTF_8)
                .build();
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .body(file.bytes());
    }
}
