package com.settle.backend.domain.action.client;

import com.settle.backend.domain.action.dto.ActionApprovalRequest;
import com.settle.backend.domain.action.dto.ActionPreviewRequest;
import com.settle.backend.domain.action.dto.AgentResponse;
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class HttpAiActionClient implements AiActionClient {
    private final RestClient restClient;

    public HttpAiActionClient(@Qualifier("aiRestClient") RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public AgentResponse preview(String actionId, String sessionId) {
        return restClient.post()
                .uri("/api/actions/{actionId}/preview", actionId)
                .body(new ActionPreviewRequest(sessionId))
                .retrieve()
                .body(AgentResponse.class);
    }

    @Override
    public AgentResponse approve(String actionId, String sessionId, boolean approved) {
        return restClient.post()
                .uri("/api/actions/{actionId}/approve", actionId)
                .body(new ActionApprovalRequest(sessionId, approved))
                .retrieve()
                .body(AgentResponse.class);
    }

    @Override
    public AgentResponse state(String sessionId) {
        return restClient.get()
                .uri(uriBuilder -> uriBuilder.path("/api/state")
                        .queryParam("session_id", sessionId)
                        .build())
                .retrieve()
                .body(AgentResponse.class);
    }

    @Override
    public List<Map<String, Object>> ledger(String sessionId) {
        List<Map<String, Object>> entries = restClient.get()
                .uri(uriBuilder -> uriBuilder.path("/api/ledger")
                        .queryParam("session_id", sessionId)
                        .build())
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
        return entries == null ? List.of() : entries;
    }

    @Override
    public byte[] downloadPdf(String pdfUrl) {
        if (pdfUrl == null || !pdfUrl.startsWith("/") || pdfUrl.startsWith("//")) {
            throw new IllegalArgumentException("invalid_ai_pdf_url");
        }
        return restClient.get()
                .uri(pdfUrl)
                .retrieve()
                .body(byte[].class);
    }
}
