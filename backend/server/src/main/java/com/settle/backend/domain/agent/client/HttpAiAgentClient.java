package com.settle.backend.domain.agent.client;

import com.settle.backend.domain.agent.dto.AgentMessageRequest;
import com.settle.backend.domain.agent.dto.AgentSessionRequest;
import java.io.IOException;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class HttpAiAgentClient implements AiAgentClient {
    private final RestClient restClient;

    public HttpAiAgentClient(@Qualifier("aiRestClient") RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public ResponseEntity<Map<String, Object>> createSession(String sessionId, String locale) {
        return restClient.post()
                .uri(builder -> builder.path("/api/session")
                        .queryParam("session_id", sessionId)
                        .queryParam("locale", locale)
                        .build())
                .exchange((upstreamRequest, upstreamResponse) -> forward(upstreamResponse));
    }

    @Override
    public ResponseEntity<Map<String, Object>> chat(AgentMessageRequest request) {
        return post("/api/chat", request);
    }

    @Override
    public ResponseEntity<Map<String, Object>> startAction(
            String actionId,
            AgentSessionRequest request
    ) {
        return restClient.post()
                .uri("/api/actions/{id}/start", actionId)
                .body(request)
                .exchange((upstreamRequest, upstreamResponse) -> forward(upstreamResponse));
    }

    private ResponseEntity<Map<String, Object>> post(String uri, Object request) {
        return restClient.post()
                .uri(uri)
                .body(request)
                .exchange((upstreamRequest, upstreamResponse) -> forward(upstreamResponse));
    }

    private ResponseEntity<Map<String, Object>> forward(
            RestClient.RequestHeadersSpec.ConvertibleClientHttpResponse response
    ) throws IOException {
        Map<String, Object> body = response.bodyTo(new ParameterizedTypeReference<>() {
        });
        return ResponseEntity.status(response.getStatusCode()).body(body);
    }
}
