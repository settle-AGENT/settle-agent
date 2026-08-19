package com.settle.backend.domain.file.controller;

import com.settle.backend.domain.file.dto.PresignedUploadRequest;
import com.settle.backend.domain.file.dto.PresignedUploadResponse;
import com.settle.backend.domain.file.service.FileService;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/uploads")
public class FileController {

    private final FileService fileService;

    public FileController(FileService fileService) {
        this.fileService = fileService;
    }

    @PostMapping
    public PresignedUploadResponse createPresignedUpload(
            @Valid @RequestBody PresignedUploadRequest request
    ) {
        // TODO 인증 구현 후 JWT subject에서 memberId를 주입한다.
        return fileService.issueUploadUrl(new UUID(0L, 0L), request);
    }
}
