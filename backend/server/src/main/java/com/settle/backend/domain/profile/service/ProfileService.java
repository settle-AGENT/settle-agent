package com.settle.backend.domain.profile.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.settle.backend.common.auth.SessionOwnership;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import com.settle.backend.domain.profile.client.AiProfileClient;
import com.settle.backend.domain.profile.dto.ProfileConfirmRequest;
import com.settle.backend.domain.profile.exception.ProfileValidationException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    private final AiProfileClient aiProfileClient;
    private final ObjectMapper objectMapper;
    private final GeneratedDocumentService documentService;

    public ProfileService(
            AiProfileClient aiProfileClient,
            ObjectMapper objectMapper,
            GeneratedDocumentService documentService
    ) {
        this.aiProfileClient = aiProfileClient;
        this.objectMapper = objectMapper;
        this.documentService = documentService;
    }

    public ResponseEntity<Map<String, Object>> confirm(
            UUID memberId, ProfileConfirmRequest request
    ) {
        SessionOwnership.require(memberId, request.sessionId());
        validateMessage(request.message());
        return documentService.withReadyReferences(
                aiProfileClient.confirm(request),
                memberId,
                request.sessionId()
        );
    }

    private void validateMessage(String message) {
        try {
            JsonNode value = objectMapper.readTree(message);
            if (value == null || !value.isObject()) {
                throw invalidMessage();
            }
        } catch (ProfileValidationException exception) {
            throw exception;
        } catch (Exception exception) {
            throw invalidMessage();
        }
    }

    private ProfileValidationException invalidMessage() {
        return new ProfileValidationException(
                "message는 수정된 필드만 담은 JSON 객체 문자열이어야 합니다.",
                List.of(Map.of("field", "message", "reason", "invalid_json_object_string"))
        );
    }
}
