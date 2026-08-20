package com.settle.backend.domain.action.controller;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.settle.backend.domain.action.dto.AgentResponse;
import com.settle.backend.domain.action.service.ActionPreviewService;
import com.settle.backend.domain.auth.service.JwtTokenService;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import java.util.Map;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ActionDocumentController.class)
class ActionDocumentControllerTest {
    private static final UUID MEMBER_ID = UUID.fromString("10000000-0000-0000-0000-000000000001");
    private static final UUID DOCUMENT_ID = UUID.fromString("20000000-0000-0000-0000-000000000002");

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private ActionPreviewService actionPreviewService;

    @MockitoBean
    private GeneratedDocumentService documentService;

    @MockitoBean
    private JwtTokenService jwtTokenService;

    @Test
    void rejectsMissingBearerTokenWithSharedErrorBody() throws Exception {
        mockMvc.perform(get("/api/ledger").queryParam("session_id", "demo-001"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail.error").value("invalid_or_missing_token"))
                .andExpect(jsonPath("$.detail.message").value("로그인이 만료되었어요. 다시 로그인해 주세요."));
    }

    @Test
    void returnsApprovalFromPreviewWithoutChangingContract() throws Exception {
        when(jwtTokenService.parseMemberId("token")).thenReturn(MEMBER_ID);
        when(actionPreviewService.preview(MEMBER_ID, "open_bank_account", "demo-001"))
                .thenReturn(new AgentResponse(
                        "1",
                        "실행할까요?",
                        new AgentResponse.Ui("approval", Map.of("action_id", "open_bank_account")),
                        Map.of("session_id", "demo-001")
                ));

        mockMvc.perform(post("/api/actions/open_bank_account/preview")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"session_id\":\"demo-001\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.schema_version").value("1"))
                .andExpect(jsonPath("$.ui.type").value("approval"));
    }

    @Test
    void servesStoredPdfInline() throws Exception {
        byte[] pdf = "%PDF-1.7 test".getBytes();
        when(jwtTokenService.parseMemberId("token")).thenReturn(MEMBER_ID);
        when(documentService.loadPdf(MEMBER_ID, DOCUMENT_ID))
                .thenReturn(new GeneratedDocumentService.DocumentFile("계좌개설신청서", pdf));

        mockMvc.perform(get("/api/documents/{documentId}/preview", DOCUMENT_ID)
                        .header(HttpHeaders.AUTHORIZATION, "Bearer token"))
                .andExpect(status().isOk())
                .andExpect(content().contentType(MediaType.APPLICATION_PDF))
                .andExpect(header().string(HttpHeaders.CONTENT_DISPOSITION, org.hamcrest.Matchers.startsWith("inline")))
                .andExpect(content().bytes(pdf));
    }

    @Test
    void forwardsApprovalDecision() throws Exception {
        when(jwtTokenService.parseMemberId("token")).thenReturn(MEMBER_ID);
        when(actionPreviewService.approve(MEMBER_ID, "open_bank_account", "demo-001", true))
                .thenReturn(new AgentResponse(
                        "1",
                        "접수되었습니다.",
                        new AgentResponse.Ui("none", Map.of()),
                        Map.of("session_id", "demo-001")
                ));

        mockMvc.perform(post("/api/actions/open_bank_account/approve")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"session_id\":\"demo-001\",\"approved\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reply").value("접수되었습니다."))
                .andExpect(jsonPath("$.state.pending_approval").doesNotExist());
    }

    @Test
    void returnsLedger() throws Exception {
        when(jwtTokenService.parseMemberId("token")).thenReturn(MEMBER_ID);
        when(actionPreviewService.ledger(MEMBER_ID, "demo-001"))
                .thenReturn(List.of(Map.of("action", "open_bank_account")));

        mockMvc.perform(get("/api/ledger")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer token")
                        .queryParam("session_id", "demo-001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].action").value("open_bank_account"));
    }
}
