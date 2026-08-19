package com.settle.backend.domain.action.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.settle.backend.domain.action.client.AiActionClient;
import com.settle.backend.domain.action.dto.AgentResponse;
import com.settle.backend.domain.document.dto.DocumentPreviewPayload;
import com.settle.backend.domain.document.entity.GeneratedDocument;
import com.settle.backend.domain.document.service.GeneratedDocumentService;
import com.settle.backend.domain.member.entity.Member;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

@ExtendWith(MockitoExtension.class)
class ActionPreviewServiceTest {
    private static final UUID MEMBER_ID = UUID.fromString("10000000-0000-0000-0000-000000000001");
    private static final UUID DOCUMENT_ID = UUID.fromString("20000000-0000-0000-0000-000000000002");

    @Mock
    private AiActionClient aiActionClient;

    @Mock
    private GeneratedDocumentService documentService;

    private ActionPreviewService service;

    @BeforeEach
    void setUp() {
        service = new ActionPreviewService(aiActionClient, documentService);
    }

    @Test
    void returnsApprovalWithoutDownloadingOrSavingPdf() {
        AgentResponse approval = new AgentResponse(
                "1",
                "실행할까요?",
                new AgentResponse.Ui("approval", Map.of("action_id", "open_bank_account")),
                Map.of("session_id", "demo-001")
        );
        when(aiActionClient.preview("open_bank_account", "demo-001")).thenReturn(approval);

        AgentResponse result = service.preview(MEMBER_ID, "open_bank_account", "demo-001");

        assertThat(result.ui()).isEqualTo(approval.ui());
        assertThat(result.state().get("documents")).isEqualTo(List.of());
        verify(aiActionClient, never()).downloadPdf(any());
        verify(documentService, never()).storePdf(any(), any(), any(), any(), any(), any());
    }

    @Test
    void storesAiPdfAndReplacesPublicDocumentUrls() {
        byte[] pdf = "%PDF-1.7 test".getBytes();
        AgentResponse aiResponse = new AgentResponse(
                "1",
                "서류를 작성했습니다.",
                new AgentResponse.Ui("doc_preview", Map.of(
                        "document_id", "doc-open-bank-account",
                        "title", "계좌개설신청서",
                        "preview_url", "/api/documents/doc-open-bank-account/preview",
                        "pdf_url", "/api/documents/doc-open-bank-account.pdf",
                        "warnings", List.of("영문 이름을 확인해 주세요.")
                )),
                Map.of(
                        "session_id", "demo-001",
                        "documents", List.of(Map.of("id", "doc-open-bank-account"))
                )
        );
        GeneratedDocument document = document();
        when(aiActionClient.preview("open_bank_account", "demo-001")).thenReturn(aiResponse);
        when(aiActionClient.downloadPdf("/api/documents/doc-open-bank-account.pdf")).thenReturn(pdf);
        when(documentService.storePdf(
                MEMBER_ID,
                "demo-001",
                "open_bank_account",
                "계좌개설신청서",
                pdf,
                List.of("영문 이름을 확인해 주세요.")
        )).thenReturn(document);
        when(documentService.listReady(MEMBER_ID, "demo-001")).thenReturn(List.of(document));

        AgentResponse result = service.preview(MEMBER_ID, "open_bank_account", "demo-001");

        DocumentPreviewPayload payload = (DocumentPreviewPayload) result.ui().payload();
        assertThat(payload.documentId()).isEqualTo(DOCUMENT_ID);
        assertThat(payload.previewUrl()).isEqualTo("/api/documents/%s/preview".formatted(DOCUMENT_ID));
        assertThat(payload.pdfUrl()).isEqualTo("/api/documents/%s/download".formatted(DOCUMENT_ID));
        assertThat(result.state().get("documents").toString()).contains(DOCUMENT_ID.toString());
    }

    @Test
    void rejectsApprovalWhenPathActionDoesNotMatchPendingAction() {
        when(aiActionClient.state("demo-001")).thenReturn(new AgentResponse(
                "1",
                "승인 대기 중",
                new AgentResponse.Ui("approval", Map.of()),
                Map.of("pending_approval", Map.of("action_id", "alien_registration"))
        ));

        assertThatThrownBy(() -> service.approve(
                MEMBER_ID,
                "open_bank_account",
                "demo-001",
                true
        )).isInstanceOf(IllegalArgumentException.class)
                .hasMessage("approval_action_mismatch");

        verify(aiActionClient, never()).approve(any(), any(), any(Boolean.class));
    }

    @Test
    void doesNotExecuteAgainWhenApprovedActionIsAlreadyInLedger() {
        AgentResponse current = new AgentResponse(
                "1",
                "이미 실행했습니다.",
                new AgentResponse.Ui("none", Map.of()),
                Map.of("session_id", "demo-001")
        );
        when(aiActionClient.state("demo-001")).thenReturn(current);
        when(aiActionClient.ledger("demo-001"))
                .thenReturn(List.of(Map.of("action", "open_bank_account")));

        AgentResponse result = service.approve(
                MEMBER_ID,
                "open_bank_account",
                "demo-001",
                true
        );

        assertThat(result.reply()).isEqualTo("이미 실행했습니다.");
        verify(aiActionClient, never()).approve(any(), any(), any(Boolean.class));
    }

    @Test
    void forwardsCancellationAndReturnsClearedPendingApproval() {
        when(aiActionClient.state("demo-001")).thenReturn(new AgentResponse(
                "1",
                "승인 대기 중",
                new AgentResponse.Ui("approval", Map.of()),
                Map.of("pending_approval", Map.of("action_id", "open_bank_account"))
        ));
        when(aiActionClient.approve("open_bank_account", "demo-001", false))
                .thenReturn(new AgentResponse(
                        "1",
                        "취소했습니다.",
                        new AgentResponse.Ui("none", Map.of()),
                        Map.of("session_id", "demo-001")
                ));

        AgentResponse result = service.approve(
                MEMBER_ID,
                "open_bank_account",
                "demo-001",
                false
        );

        assertThat(result.state()).doesNotContainKey("pending_approval");
        verify(aiActionClient).approve("open_bank_account", "demo-001", false);
    }

    private GeneratedDocument document() {
        GeneratedDocument document = new GeneratedDocument(
                DOCUMENT_ID,
                new Member("member@example.com", "password-hash"),
                "demo-001",
                "open_bank_account",
                "계좌개설신청서",
                "members/member/generated-documents/document.pdf"
        );
        document.markReady(List.of());
        ReflectionTestUtils.setField(document, "createdAt", Instant.parse("2026-08-19T00:00:00Z"));
        return document;
    }
}
