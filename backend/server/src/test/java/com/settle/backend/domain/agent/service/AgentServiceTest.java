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
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

class AgentServiceTest {
    private static final UUID MEMBER_ID = UUID.randomUUID();
    private final AiAgentClient aiAgentClient = mock(AiAgentClient.class);
    private final AgentService agentService = new AgentService(aiAgentClient);

    @Test
    void forwardsChatResponseWithoutChangingAgentEnvelope() {
        AgentMessageRequest request = new AgentMessageRequest(MEMBER_ID.toString(), "고려대학교");
        ResponseEntity<Map<String, Object>> upstream = ResponseEntity.ok(Map.of(
                "ui", Map.of("type", "comparison"),
                "state", Map.of("session_id", MEMBER_ID.toString()),
                "reply", "은행별 요건을 비교했습니다."
        ));
        when(aiAgentClient.chat(request)).thenReturn(upstream);

        assertThat(agentService.chat(MEMBER_ID, request)).isSameAs(upstream);
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

        assertThat(agentService.startAction(MEMBER_ID, "open_account", request)).isSameAs(upstream);
        verify(aiAgentClient).startAction("open_account", request);
    }

    @Test
    void createsStableSessionFromMemberId() {
        ResponseEntity<Map<String, Object>> upstream = ResponseEntity.ok(Map.of(
                "state", Map.of("session_id", MEMBER_ID.toString())
        ));
        when(aiAgentClient.createSession(MEMBER_ID.toString(), "ko")).thenReturn(upstream);

        assertThat(agentService.createSession(MEMBER_ID, "ko")).isSameAs(upstream);
        verify(aiAgentClient).createSession(MEMBER_ID.toString(), "ko");
    }

    @Test
    void rejectsAnotherMembersSessionBeforeCallingAi() {
        AgentMessageRequest request = new AgentMessageRequest(UUID.randomUUID().toString(), "answer");

        assertThatThrownBy(() -> agentService.chat(MEMBER_ID, request))
                .isInstanceOf(SessionAccessDeniedException.class);
    }
}
