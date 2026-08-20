package com.settle.backend.domain.agent.client;

import com.settle.backend.domain.agent.dto.AgentMessageRequest;
import com.settle.backend.domain.agent.dto.AgentSessionRequest;
import java.util.Map;
import org.springframework.http.ResponseEntity;

public interface AiAgentClient {
    ResponseEntity<Map<String, Object>> createSession(String sessionId, String locale);

    ResponseEntity<Map<String, Object>> chat(AgentMessageRequest request);

    ResponseEntity<Map<String, Object>> startAction(String actionId, AgentSessionRequest request);
}
