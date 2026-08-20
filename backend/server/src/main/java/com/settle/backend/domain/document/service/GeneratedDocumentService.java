package com.settle.backend.domain.document.service;

import com.settle.backend.common.exception.ResourceNotFoundException;
import com.settle.backend.domain.document.entity.GeneratedDocument;
import com.settle.backend.domain.document.entity.GeneratedDocumentStatus;
import com.settle.backend.domain.document.repository.GeneratedDocumentRepository;
import com.settle.backend.domain.file.service.S3FileGateway;
import com.settle.backend.domain.member.entity.Member;
import com.settle.backend.domain.member.repository.MemberRepository;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class GeneratedDocumentService {
    private static final byte[] PDF_SIGNATURE = {'%', 'P', 'D', 'F', '-'};

    private final MemberRepository memberRepository;
    private final GeneratedDocumentRepository documentRepository;
    private final S3FileGateway s3;

    public GeneratedDocumentService(
            MemberRepository memberRepository,
            GeneratedDocumentRepository documentRepository,
            S3FileGateway s3
    ) {
        this.memberRepository = memberRepository;
        this.documentRepository = documentRepository;
        this.s3 = s3;
    }

    public GeneratedDocument storePdf(
            UUID memberId,
            String sessionId,
            String actionId,
            String title,
            byte[] pdf,
            List<String> warnings
    ) {
        validatePdf(pdf);
        Member member = memberRepository.findById(memberId)
                .orElseThrow(() -> new ResourceNotFoundException("사용자를 찾을 수 없습니다: " + memberId));
        UUID documentId = UUID.randomUUID();
        String objectKey = "members/%s/generated-documents/%s.pdf"
                .formatted(memberId, documentId);
        GeneratedDocument document = documentRepository.save(new GeneratedDocument(
                documentId,
                member,
                sessionId,
                actionId,
                title,
                objectKey
        ));

        try {
            s3.uploadPdf(objectKey, pdf);
            document.markReady(warnings);
            return documentRepository.save(document);
        } catch (RuntimeException exception) {
            document.markFailed();
            documentRepository.save(document);
            throw exception;
        }
    }

    public DocumentFile loadPdf(UUID memberId, UUID documentId) {
        GeneratedDocument document = documentRepository.findByIdAndMember_Id(documentId, memberId)
                .filter(candidate -> candidate.getStatus() == GeneratedDocumentStatus.READY)
                .orElseThrow(() -> new ResourceNotFoundException("문서를 찾을 수 없습니다: " + documentId));
        S3FileGateway.StoredFile stored = s3.download(document.getObjectKey());
        validatePdf(stored.bytes());
        return new DocumentFile(document.getTitle(), stored.bytes());
    }

    public List<GeneratedDocument> listReady(UUID memberId, String sessionId) {
        return documentRepository.findAllByMember_IdAndSessionIdAndStatusOrderByCreatedAtDesc(
                memberId,
                sessionId,
                GeneratedDocumentStatus.READY
        );
    }

    private void validatePdf(byte[] pdf) {
        if (pdf == null || pdf.length < PDF_SIGNATURE.length) {
            throw new IllegalArgumentException("invalid_pdf");
        }
        for (int index = 0; index < PDF_SIGNATURE.length; index++) {
            if (pdf[index] != PDF_SIGNATURE[index]) {
                throw new IllegalArgumentException("invalid_pdf");
            }
        }
    }

    public record DocumentFile(String title, byte[] bytes) {
    }
}
