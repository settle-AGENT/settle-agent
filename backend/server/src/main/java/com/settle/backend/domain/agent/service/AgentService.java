package com.settle.backend.domain.agent.service;

import com.settle.backend.domain.agent.client.AiAgentClient;
import com.settle.backend.domain.agent.dto.AgentMessageRequest;
import com.settle.backend.domain.agent.dto.AgentSessionRequest;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;

@Service
public class AgentService {
    private final AiAgentClient aiAgentClient;

    public AgentService(AiAgentClient aiAgentClient) {
        this.aiAgentClient = aiAgentClient;
    }

    public ResponseEntity<Map<String, Object>> createSession(UUID memberId, String locale) {
        return aiAgentClient.createSession(memberId.toString(), locale);
    }

    public ResponseEntity<Map<String, Object>> chat(UUID memberId, AgentMessageRequest request) {
        requireOwnSession(memberId, request.sessionId());
        return aiAgentClient.chat(request);
    }

    public ResponseEntity<Map<String, Object>> startAction(
            UUID memberId, String actionId,
            AgentSessionRequest request
    ) {
        requireOwnSession(memberId, request.sessionId());
        return aiAgentClient.startAction(actionId, request);
    }

    private void requireOwnSession(UUID memberId, String sessionId) {
        if (!memberId.toString().equals(sessionId)) {
            throw new org.springframework.web.server.ResponseStatusException(
                    HttpStatus.FORBIDDEN, "session_access_denied"
            );
        }
    }
}
