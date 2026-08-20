package com.settle.backend.domain.action.client;

import com.settle.backend.domain.action.dto.AgentResponse;
import java.util.List;
import java.util.Map;

public interface AiActionClient {
    AgentResponse preview(String actionId, String sessionId);

    AgentResponse approve(String actionId, String sessionId, boolean approved);

    AgentResponse state(String sessionId);

    List<Map<String, Object>> ledger(String sessionId);

    byte[] downloadPdf(String pdfUrl);
}
