package com.settle.backend.domain.agent.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.settle.backend.common.auth.SessionAccessDeniedException;
import com.settle.backend.domain.agent.client.AiAgentClient;
import com.settle.backend.domain.agent.dto.AgentMessageRequest;
import com.settle.backend.domain.agent.dto.AgentSessionRequest;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

class AgentServiceTest {
    private static final UUID MEMBER_ID = UUID.randomUUID();
    private final AiAgentClient aiAgentClient = mock(AiAgentClient.class);
    private final GeneratedDocumentService documentService = mock(GeneratedDocumentService.class);
    private final AgentService agentService = new AgentService(aiAgentClient, documentService);

    @Test
    void addsStoredDocumentsWithoutChangingOtherChatFields() {
        AgentMessageRequest request = new AgentMessageRequest(MEMBER_ID.toString(), "고려대학교");
        ResponseEntity<Map<String, Object>> upstream = ResponseEntity.ok(Map.of(
                "ui", Map.of("type", "comparison"),
                "state", Map.of("session_id", MEMBER_ID.toString()),
                "reply", "은행별 요건을 비교했습니다."
        ));
        when(aiAgentClient.chat(request)).thenReturn(upstream);
        when(documentService.withReadyReferences(upstream, MEMBER_ID, MEMBER_ID.toString()))
                .thenReturn(ResponseEntity.ok(Map.of(
                        "ui", Map.of("type", "comparison"),
                        "state", Map.of("session_id", MEMBER_ID.toString(), "documents", List.of()),
                        "reply", "은행별 요건을 비교했습니다."
                )));

        Map<String, Object> body = agentService.chat(MEMBER_ID, request).getBody();
        assertThat(body).isNotNull();
        assertThat(((Map<?, ?>) body.get("state")).get("documents")).isEqualTo(List.of());
        verify(aiAgentClient).chat(request);
    }

    @Test
    void forwardsLockedActionErrorStatusAndBody() {
        AgentSessionRequest request = new AgentSessionRequest(MEMBER_ID.toString());
        ResponseEntity<Map<String, Object>> upstream = ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("detail", Map.of(
                        "error", "prerequisite_missing",
                        "message", "먼저 완료해야 합니다: 외국인등록"
                )));
        when(aiAgentClient.startAction("open_account", request)).thenReturn(upstream);
        when(documentService.withReadyReferences(upstream, MEMBER_ID, MEMBER_ID.toString()))
                .thenReturn(upstream);

        assertThat(agentService.startAction(MEMBER_ID, "open_account", request)).isSameAs(upstream);
        verify(aiAgentClient).startAction("open_account", request);
    }

    @Test
    void createsStableSessionFromMemberId() {
        ResponseEntity<Map<String, Object>> upstream = ResponseEntity.ok(Map.of(
                "state", Map.of(
                        "session_id", MEMBER_ID.toString(),
                        "documents", List.of(Map.of(
                                "id", "ai-document-id",
                                "preview_url", "/api/documents/ai-document-id/preview"
                        ))
                )
        ));
        List<Map<String, Object>> storedDocuments = List.of(Map.of(
                "id", "spring-document-id",
                "preview_url", "/api/documents/spring-document-id/preview"
        ));
        when(aiAgentClient.createSession(MEMBER_ID.toString(), "ko", false, null)).thenReturn(upstream);
        when(documentService.withReadyReferences(upstream, MEMBER_ID, MEMBER_ID.toString()))
                .thenReturn(ResponseEntity.ok(Map.of(
                        "state", Map.of(
                                "session_id", MEMBER_ID.toString(),
                                "documents", storedDocuments
                        )
                )));

        assertThat(agentService.createSession(MEMBER_ID, "ko", false, false, null, null).getBody())
                .extracting(body -> ((Map<?, ?>) body.get("state")).get("documents"))
                .isEqualTo(storedDocuments);
        verify(aiAgentClient).createSession(MEMBER_ID.toString(), "ko", false, null);
    }

    @Test
    void rejectsAnotherMembersSessionBeforeCallingAi() {
        AgentMessageRequest request = new AgentMessageRequest(UUID.randomUUID().toString(), "answer");

        assertThatThrownBy(() -> agentService.chat(MEMBER_ID, request))
                .isInstanceOf(SessionAccessDeniedException.class);
    }
}
