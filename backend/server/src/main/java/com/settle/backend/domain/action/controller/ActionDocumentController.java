package com.settle.backend.domain.action.controller;

import com.settle.backend.domain.action.dto.ActionApprovalRequest;
import com.settle.backend.domain.action.dto.ActionPreviewRequest;
import com.settle.backend.domain.action.dto.AgentResponse;
import com.settle.backend.domain.action.service.ActionPreviewService;
import com.settle.backend.domain.auth.exception.InvalidCredentialsException;
import com.settle.backend.domain.auth.service.JwtTokenService;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
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
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ActionDocumentController {
    private static final String BEARER_PREFIX = "Bearer ";

    private final ActionPreviewService actionPreviewService;
    private final GeneratedDocumentService documentService;
    private final JwtTokenService jwtTokenService;

    public ActionDocumentController(
            ActionPreviewService actionPreviewService,
            GeneratedDocumentService documentService,
            JwtTokenService jwtTokenService
    ) {
        this.actionPreviewService = actionPreviewService;
        this.documentService = documentService;
        this.jwtTokenService = jwtTokenService;
    }

    @PostMapping("/api/actions/{actionId}/preview")
    public AgentResponse preview(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization,
            @PathVariable String actionId,
            @Valid @RequestBody ActionPreviewRequest request
    ) {
        return actionPreviewService.preview(memberId(authorization), actionId, request.sessionId());
    }

    @PostMapping("/api/actions/{actionId}/approve")
    public AgentResponse approve(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization,
            @PathVariable String actionId,
            @Valid @RequestBody ActionApprovalRequest request
    ) {
        return actionPreviewService.approve(
                memberId(authorization),
                actionId,
                request.sessionId(),
                request.approved()
        );
    }

    @GetMapping("/api/ledger")
    public List<Map<String, Object>> ledger(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization,
            @RequestParam("session_id") String sessionId
    ) {
        memberId(authorization);
        return actionPreviewService.ledger(sessionId);
    }

    @GetMapping("/api/documents/{documentId}/preview")
    public ResponseEntity<byte[]> viewDocument(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization,
            @PathVariable UUID documentId
    ) {
        return pdfResponse(memberId(authorization), documentId, false);
    }

    @GetMapping("/api/documents/{documentId}/download")
    public ResponseEntity<byte[]> downloadDocument(
            @RequestHeader(value = HttpHeaders.AUTHORIZATION, required = false) String authorization,
            @PathVariable UUID documentId
    ) {
        return pdfResponse(memberId(authorization), documentId, true);
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

    private UUID memberId(String authorization) {
        if (authorization == null || !authorization.startsWith(BEARER_PREFIX)) {
            throw new InvalidCredentialsException();
        }
        try {
            return jwtTokenService.parseMemberId(authorization.substring(BEARER_PREFIX.length()));
        } catch (RuntimeException exception) {
            throw new InvalidCredentialsException();
        }
    }
}
