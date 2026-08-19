package com.settle.backend.domain.file.controller;

import com.settle.backend.domain.file.dto.PresignedUploadRequest;
import com.settle.backend.domain.file.dto.PresignedUploadResponse;
import com.settle.backend.domain.file.service.FileService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
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
            @ApiResponse(responseCode = "200", description = "presigned PUT URL 발급 성공"),
            @ApiResponse(responseCode = "422", description = "documentType 검증 실패")
    })
    public PresignedUploadResponse createPresignedUpload(
            @Valid @RequestBody PresignedUploadRequest request
    ) {
        // TODO 인증 구현 후 JWT subject에서 memberId를 주입한다.
        return fileService.issueUploadUrl(new UUID(0L, 0L), request);
    }
}
