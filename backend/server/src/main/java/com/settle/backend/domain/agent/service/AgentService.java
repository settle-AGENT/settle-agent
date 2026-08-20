package com.settle.backend.domain.agent.service;

import com.settle.backend.common.auth.SessionOwnership;
import com.settle.backend.domain.agent.client.AiAgentClient;
import com.settle.backend.domain.agent.dto.AgentMessageRequest;
import com.settle.backend.domain.agent.dto.AgentSessionRequest;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;

@Service
public class AgentService {
    private final AiAgentClient aiAgentClient;
    private final GeneratedDocumentService documentService;

    public AgentService(
            AiAgentClient aiAgentClient,
            GeneratedDocumentService documentService
    ) {
        this.aiAgentClient = aiAgentClient;
        this.documentService = documentService;
    }

    public ResponseEntity<Map<String, Object>> createSession(UUID memberId, String locale) {
        String sessionId = memberId.toString();
        return documentService.withReadyReferences(
                aiAgentClient.createSession(sessionId, locale),
                memberId,
                sessionId
        );
    }

    public ResponseEntity<Map<String, Object>> chat(UUID memberId, AgentMessageRequest request) {
        SessionOwnership.require(memberId, request.sessionId());
        return documentService.withReadyReferences(
                aiAgentClient.chat(request),
                memberId,
                request.sessionId()
        );
    }

    public ResponseEntity<Map<String, Object>> startAction(
            UUID memberId, String actionId,
            AgentSessionRequest request
    ) {
        SessionOwnership.require(memberId, request.sessionId());
        return documentService.withReadyReferences(
                aiAgentClient.startAction(actionId, request),
                memberId,
                request.sessionId()
        );
    }
}
