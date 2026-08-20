package com.settle.backend.domain.document.client;

import com.settle.backend.domain.file.entity.DocumentType;
import java.util.Map;
import org.springframework.http.ResponseEntity;

public interface AiDocumentClient {

    ResponseEntity<Map<String, Object>> extract(
            String sessionId, byte[] image, DocumentType documentType
    );
}
