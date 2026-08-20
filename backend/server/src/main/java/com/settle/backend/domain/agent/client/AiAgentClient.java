package com.settle.backend.domain.agent.client;

import com.settle.backend.domain.agent.dto.AgentMessageRequest;
import com.settle.backend.domain.agent.dto.AgentSessionRequest;
import java.util.Map;
import java.util.function.Consumer;
import org.springframework.http.ResponseEntity;

public interface AiAgentClient {
    ResponseEntity<Map<String, Object>> createSession(
            String sessionId, String locale, boolean reset, String sourceSessionId
    );

    ResponseEntity<Map<String, Object>> chat(AgentMessageRequest request);
    void streamChat(AgentMessageRequest request, Consumer<String> onData);

    ResponseEntity<Map<String, Object>> startAction(String actionId, AgentSessionRequest request);
}
