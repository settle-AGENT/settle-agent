package com.settle.backend.domain.agent.service;

import com.settle.backend.common.auth.SessionOwnership;
import com.settle.backend.domain.agent.client.AiAgentClient;
import com.settle.backend.domain.agent.dto.AgentMessageRequest;
import com.settle.backend.domain.agent.dto.AgentSessionRequest;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import java.util.concurrent.CompletableFuture;
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

    public ResponseEntity<Map<String, Object>> createSession(
            UUID memberId,
            String locale,
            boolean reset,
            boolean fresh,
            String requestedSessionId,
            String sourceSessionId
    ) {
        if (requestedSessionId != null && !requestedSessionId.isBlank()) {
            SessionOwnership.require(memberId, requestedSessionId);
        }
        if (sourceSessionId != null && !sourceSessionId.isBlank()) {
            SessionOwnership.require(memberId, sourceSessionId);
        }
        String sessionId = fresh
                ? SessionOwnership.freshId(memberId)
                : requestedSessionId == null || requestedSessionId.isBlank()
                        ? memberId.toString()
                        : requestedSessionId;
        return documentService.withReadyReferences(
                aiAgentClient.createSession(sessionId, locale, reset, fresh ? sourceSessionId : null),
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

    public SseEmitter chatStream(UUID memberId, AgentMessageRequest request) {
        SessionOwnership.require(memberId, request.sessionId());
        SseEmitter emitter = new SseEmitter(120_000L);
        CompletableFuture.runAsync(() -> {
            try {
                aiAgentClient.streamChat(request, data -> {
                    try {
                        emitter.send(SseEmitter.event().data(data));
                    } catch (Exception exc) {
                        throw new IllegalStateException(exc);
                    }
                });
                emitter.complete();
            } catch (Exception exc) {
                emitter.completeWithError(exc);
            }
        });
        return emitter;
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
