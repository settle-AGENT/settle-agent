package com.settle.backend.domain.document.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.settle.backend.domain.document.entity.GeneratedDocument;
import com.settle.backend.domain.document.entity.GeneratedDocumentStatus;
import com.settle.backend.domain.document.repository.GeneratedDocumentRepository;
import com.settle.backend.domain.file.service.S3FileGateway;
import com.settle.backend.domain.member.entity.Member;
import com.settle.backend.domain.member.repository.MemberRepository;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class GeneratedDocumentServiceTest {
    private static final UUID MEMBER_ID = UUID.fromString("10000000-0000-0000-0000-000000000001");

    @Mock
    private MemberRepository memberRepository;

    @Mock
    private GeneratedDocumentRepository documentRepository;

    @Mock
    private S3FileGateway s3;

    private GeneratedDocumentService service;

    @BeforeEach
    void setUp() {
        service = new GeneratedDocumentService(memberRepository, documentRepository, s3);
    }

    @Test
    void storesPdfInS3AndMarksDocumentReady() {
        byte[] pdf = "%PDF-1.7 test".getBytes(StandardCharsets.US_ASCII);
        when(memberRepository.findById(MEMBER_ID))
                .thenReturn(Optional.of(new Member("member@example.com", "password-hash")));
        when(documentRepository.save(any(GeneratedDocument.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        GeneratedDocument document = service.storePdf(
                MEMBER_ID,
                "demo-001",
                "open_bank_account",
                "계좌개설신청서",
                pdf,
                List.of()
        );

        verify(s3).uploadPdf(document.getObjectKey(), pdf);
        verify(documentRepository, times(2)).save(document);
        assertThat(document.getObjectKey())
                .isEqualTo("members/%s/generated-documents/%s.pdf"
                        .formatted(MEMBER_ID, document.getId()));
        assertThat(document.getStatus()).isEqualTo(GeneratedDocumentStatus.READY);
    }

    @Test
    void rejectsNonPdfBeforeAccessingStorage() {
        assertThatThrownBy(() -> service.storePdf(
                MEMBER_ID,
                "demo-001",
                "open_bank_account",
                "계좌개설신청서",
                "not-pdf".getBytes(StandardCharsets.US_ASCII),
                List.of()
        )).isInstanceOf(IllegalArgumentException.class)
                .hasMessage("invalid_pdf");

        verify(memberRepository, never()).findById(any());
        verify(documentRepository, never()).save(any());
        verify(s3, never()).uploadPdf(anyString(), any());
    }

    @Test
    void marksDocumentFailedWhenS3UploadFails() {
        byte[] pdf = "%PDF-1.7 test".getBytes(StandardCharsets.US_ASCII);
        when(memberRepository.findById(MEMBER_ID))
                .thenReturn(Optional.of(new Member("member@example.com", "password-hash")));
        when(documentRepository.save(any(GeneratedDocument.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));
        doThrow(new IllegalStateException("s3_failed"))
                .when(s3).uploadPdf(anyString(), any());

        assertThatThrownBy(() -> service.storePdf(
                MEMBER_ID,
                "demo-001",
                "open_bank_account",
                "계좌개설신청서",
                pdf,
                List.of()
        )).isInstanceOf(IllegalStateException.class)
                .hasMessage("s3_failed");

        ArgumentCaptor<GeneratedDocument> documentCaptor = ArgumentCaptor.forClass(GeneratedDocument.class);
        verify(documentRepository, times(2)).save(documentCaptor.capture());
        assertThat(documentCaptor.getValue().getStatus()).isEqualTo(GeneratedDocumentStatus.FAILED);
    }
}
