package com.settle.backend.domain.action.controller;

import com.settle.backend.common.auth.CurrentMemberId;
import com.settle.backend.domain.action.dto.ActionApprovalRequest;
import com.settle.backend.domain.action.dto.ActionPreviewRequest;
import com.settle.backend.domain.action.dto.AgentResponse;
import com.settle.backend.domain.action.service.ActionPreviewService;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import io.swagger.v3.oas.annotations.Parameter;
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
    public AgentResponse preview(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @PathVariable String actionId,
            @Valid @RequestBody ActionPreviewRequest request
    ) {
        return actionPreviewService.preview(memberId, actionId, request.sessionId());
    }

    @PostMapping("/api/actions/{actionId}/approve")
    public AgentResponse approve(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
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
    public List<Map<String, Object>> ledger(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @RequestParam("session_id") String sessionId
    ) {
        return actionPreviewService.ledger(sessionId);
    }

    @GetMapping("/api/documents/{documentId}/preview")
    public ResponseEntity<byte[]> viewDocument(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
            @PathVariable UUID documentId
    ) {
        return pdfResponse(memberId, documentId, false);
    }

    @GetMapping("/api/documents/{documentId}/download")
    public ResponseEntity<byte[]> downloadDocument(
            @Parameter(hidden = true) @CurrentMemberId UUID memberId,
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
