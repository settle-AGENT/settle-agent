package com.settle.backend.domain.document.service;

import com.settle.backend.domain.document.client.AiDocumentClient;
import com.settle.backend.domain.document.dto.ExtractDocumentRequest;
import com.settle.backend.domain.file.service.FileService;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final FileService fileService;
    private final AiDocumentClient aiDocumentClient;

    public DocumentService(FileService fileService, AiDocumentClient aiDocumentClient) {
        this.fileService = fileService;
        this.aiDocumentClient = aiDocumentClient;
    }

    public ResponseEntity<Map<String, Object>> extractAndSave(
            UUID memberId, ExtractDocumentRequest request
    ) {
        FileService.PreparedUpload prepared = fileService.prepareForExtraction(memberId, request.uploadId());
        try {
            ResponseEntity<Map<String, Object>> response = aiDocumentClient.extract(
                    memberId.toString(),
                    prepared.bytes(),
                    prepared.ticket().documentType()
            );
            if (response.getStatusCode().is2xxSuccessful()) {
                fileService.markDone(prepared.ticket());
                return ResponseEntity.status(HttpStatus.CREATED).body(response.getBody());
            }
            fileService.markFailed(prepared.ticket());
            return response;
        } catch (RuntimeException exception) {
            fileService.markFailed(prepared.ticket());
            throw exception;
        }
    }
}
