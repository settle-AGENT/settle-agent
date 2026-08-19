package com.settle.backend.domain.profile.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.settle.backend.domain.profile.client.AiProfileClient;
import com.settle.backend.domain.profile.dto.ProfileConfirmRequest;
import com.settle.backend.domain.profile.exception.ProfileValidationException;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    private final AiProfileClient aiProfileClient;
    private final ObjectMapper objectMapper;

    public ProfileService(AiProfileClient aiProfileClient, ObjectMapper objectMapper) {
        this.aiProfileClient = aiProfileClient;
        this.objectMapper = objectMapper;
    }

    public ResponseEntity<Map<String, Object>> confirm(ProfileConfirmRequest request) {
        validateMessage(request.message());
        return aiProfileClient.confirm(request);
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
