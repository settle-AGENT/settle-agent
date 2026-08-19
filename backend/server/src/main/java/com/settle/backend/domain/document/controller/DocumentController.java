package com.settle.backend.domain.document.controller;

import com.settle.backend.domain.document.dto.ExtractDocumentRequest;
import com.settle.backend.domain.document.service.DocumentService;
import jakarta.validation.Valid;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/documents")
public class DocumentController {

    private final DocumentService documentService;

    public DocumentController(DocumentService documentService) {
        this.documentService = documentService;
    }

    @PostMapping("/extractions")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> extractDocument(
            @Valid @RequestBody ExtractDocumentRequest request
    ) {
        // TODO 인증 구현 후 JWT subject에서 memberId를 주입한다.
        return documentService.extractAndSave(new UUID(0L, 0L), request);
    }
}
