package com.settle.backend.domain.file.controller;

import com.settle.backend.common.auth.CurrentMemberId;
import com.settle.backend.domain.file.dto.PresignedUploadRequest;
import com.settle.backend.domain.file.dto.PresignedUploadResponse;
import com.settle.backend.domain.file.service.FileService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/uploads")
@Tag(
        name = "AI OCR 업로드",
        description = "AI OCR 전 단계로, PNG를 S3에 올릴 presigned PUT URL과 uploadId를 발급합니다."
)
@SecurityRequirement(name = "bearerAuth")
public class FileController {

    private final FileService fileService;

    public FileController(FileService fileService) {
        this.fileService = fileService;
    }

    @PostMapping
    @Operation(
            summary = "OCR용 PNG 업로드 URL 발급",
            description = """
                    1. 이 API에서 `uploadId`, `uploadUrl`을 받습니다.
                    2. 브라우저가 `uploadUrl`에 `Content-Type: image/png`으로 PUT 합니다.
                    3. `uploadId`를 `POST /api/v1/documents/extractions`에 전달합니다.

                    `objectKey`는 Spring 내부에만 저장하며 프론트나 AI에 노출하지 않습니다.
                    """
    )
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "presigned PUT URL 발급 성공",
                    content = @Content(examples = @ExampleObject(value = """
                            {"uploadId":"8c83fcab-0f4b-4ce6-9f2d-c9df3cfe6e11","uploadUrl":"https://bucket.s3.ap-northeast-2.amazonaws.com/...?X-Amz-Signature=...","expiresInSeconds":300}
                            """))),
            @ApiResponse(responseCode = "401", description = "Bearer token 누락 또는 무효"),
            @ApiResponse(responseCode = "422", description = "documentType 누락 또는 검증 실패",
                    content = @Content(examples = @ExampleObject(value = """
                            {"detail":{"error":"validation_failed","message":"요청 값을 확인해 주세요.","details":[{"field":"documentType","reason":"must not be null"}]}}
                            """)))
    })
    public PresignedUploadResponse createPresignedUpload(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @Valid @RequestBody PresignedUploadRequest request
    ) {
        return fileService.issueUploadUrl(memberId, request);
    }
}
