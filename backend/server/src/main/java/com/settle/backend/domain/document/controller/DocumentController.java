package com.settle.backend.domain.document.controller;

import com.settle.backend.common.auth.CurrentMemberId;
import com.settle.backend.domain.document.dto.ExtractDocumentRequest;
import com.settle.backend.domain.document.service.DocumentService;
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
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/documents")
@Tag(
        name = "문서 OCR",
        description = "S3에 업로드한 신분증·여권을 AI 서버로 전달해 OCR 결과를 추출합니다."
)
@SecurityRequirement(name = "bearerAuth")
public class DocumentController {

    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping("/extractions")
    @Operation(
            summary = "업로드 문서 OCR 추출",
            description = """
                    `POST /api/v1/uploads`로 발급받은 `uploadId`를 전달하면,
                    S3 업로드 완료 여부와 PNG 형식을 검증한 뒤 AI OCR을 실행합니다.
                    성공 응답은 `state`, `ui`, `reply`를 포함한 AgentResponse입니다.

                    Spring→AI 내부 호출 계약:
                    `POST ${AI_BASE_URL}/api/profile/extract-upload` (multipart/form-data)
                    - `session_id`: JWT memberId 문자열
                    - `doc_type`: `arc_front | arc_back | passport`
                    - `file`: S3에서 다운로드한 PNG binary

                    AI의 AgentResponse는 Spring이 필드를 변형하지 않고 프론트에 전달합니다.
                    """
    )
    @ApiResponses({
            @ApiResponse(
                    responseCode = "201",
                    description = "OCR 추출 성공 — AI AgentResponse 그대로 반환",
                    content = @Content(
                            mediaType = "application/json",
                            schema = @Schema(type = "object"),
                            examples = @ExampleObject(value = """
                                    {
                                      "schema_version": "1",
                                      "reply": "신분증을 확인했습니다. 1개 항목은 확인이 필요합니다.",
                                      "ui": {
                                        "type": "profile_confirm",
                                        "payload": {
                                          "doc_type": "arc_front",
                                          "fields": [
                                            {
                                              "key": "nationality",
                                              "label": "Nationality",
                                              "value": "VNM",
                                              "confidence": 0.86,
                                              "editable": true
                                            },
                                            {
                                              "key": "arc_no",
                                              "label": "Registration No.",
                                              "value": "031120-*******",
                                              "confidence": 0.99,
                                              "editable": false
                                            }
                                          ]
                                        }
                                      },
                                      "state": {
                                        "session_id": "8c83fcab-0f4b-4ce6-9f2d-c9df3cfe6e11",
                                        "locale": "ko",
                                        "profile": {
                                          "nationality": "VNM",
                                          "arc_no": "031120-*******"
                                        },
                                        "tasks": [],
                                        "documents": [],
                                        "pending_approval": null
                                      }
                                    }
                                    """)
                    )
            ),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "404", description = "uploadId가 없거나 현재 사용자의 업로드가 아님",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"internal","message":"internal","details":null}}
                            """))),
            @ApiResponse(responseCode = "409", description = "업로드 미완료, 처리 중 또는 이미 처리된 업로드",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"upload_not_completed","message":"upload_not_completed","details":null}}
                            """))),
            @ApiResponse(responseCode = "415", description = "S3 Content-Type 또는 파일 시그니처가 PNG가 아님",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"unsupported_media_type","message":"unsupported_media_type","details":null}}
                            """))),
            @ApiResponse(responseCode = "422", description = "AI OCR 추출 실패—AI error body를 그대로 전달",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"extraction_failed","message":"문서를 인식하지 못했습니다.","details":{}}}
                            """))),
            @ApiResponse(responseCode = "5XX", description = "AI upstream 5xx는 같은 status/body로 전달")
    })
    public ResponseEntity<Map<String, Object>> extractDocument(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Valid @RequestBody ExtractDocumentRequest request
    ) {
        return documentService.extractAndSave(memberId, request);
    }
}
