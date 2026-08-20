package com.settle.backend.domain.document.service;

import com.settle.backend.common.exception.ResourceNotFoundException;
import com.settle.backend.domain.document.entity.GeneratedDocument;
import com.settle.backend.domain.document.entity.GeneratedDocumentStatus;
import com.settle.backend.domain.document.repository.GeneratedDocumentRepository;
import com.settle.backend.domain.file.service.S3FileGateway;
import com.settle.backend.domain.member.entity.Member;
import com.settle.backend.domain.member.repository.MemberRepository;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
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
                .filter(candidate -> candidate.getStatus() == GeneratedDocumentStatus.READY
                        || candidate.getStatus() == GeneratedDocumentStatus.ISSUED)
                .orElseThrow(() -> new ResourceNotFoundException("문서를 찾을 수 없습니다: " + documentId));
        S3FileGateway.StoredFile stored = s3.download(document.getObjectKey());
        validatePdf(stored.bytes());
        return new DocumentFile(document.getTitle(), stored.bytes());
    }

    public List<GeneratedDocument> listReady(UUID memberId, String sessionId) {
        // 서류함은 상담 세션이 아니라 회원 소유 자산이다. 새 문서 상담을 열어도
        // 이전 세션에서 만든 문서와 이력이 사라져 보이면 안 된다.
        return documentRepository.findAllByMember_IdAndStatusInOrderByCreatedAtDesc(
                memberId,
                List.of(GeneratedDocumentStatus.READY, GeneratedDocumentStatus.ISSUED)
        );
    }

    public void issueLatest(UUID memberId, String sessionId, String actionId) {
        documentRepository.findFirstByMember_IdAndSessionIdAndActionIdAndStatusOrderByCreatedAtDesc(
                memberId, sessionId, actionId, GeneratedDocumentStatus.READY
        ).ifPresent(document -> {
            document.markIssued();
            documentRepository.save(document);
        });
    }

    public List<Map<String, Object>> listIssuedHistory(UUID memberId) {
        return documentRepository.findAllByMember_IdAndStatusOrderByCreatedAtDesc(
                memberId, GeneratedDocumentStatus.ISSUED
        ).stream().map(document -> Map.<String, Object>of(
                "action", document.getTitle(),
                "action_id", document.getActionId(),
                "document_id", document.getId().toString(),
                "approved_at", document.getUpdatedAt()
        )).toList();
    }

    public List<Map<String, Object>> listReadyReferences(UUID memberId, String sessionId) {
        return listReady(memberId, sessionId).stream()
                .map(this::reference)
                .toList();
    }

    public ResponseEntity<Map<String, Object>> withReadyReferences(
            ResponseEntity<Map<String, Object>> response,
            UUID memberId,
            String sessionId
    ) {
        Map<String, Object> body = response.getBody();
        if (!response.getStatusCode().is2xxSuccessful() || body == null) {
            return response;
        }

        Map<String, Object> enrichedBody = new LinkedHashMap<>(body);
        Map<String, Object> state = mutableMap(body.get("state"));
        state.put("documents", listReadyReferences(memberId, sessionId));
        enrichedBody.put("state", state);
        return ResponseEntity.status(response.getStatusCode())
                .headers(response.getHeaders())
                .body(enrichedBody);
    }

    private Map<String, Object> reference(GeneratedDocument document) {
        Map<String, Object> reference = new LinkedHashMap<>();
        reference.put("id", document.getId().toString());
        reference.put("title", document.getTitle());
        reference.put("action_id", document.getActionId());
        reference.put("session_id", document.getSessionId());
        reference.put("status", document.getStatus() == GeneratedDocumentStatus.ISSUED ? "issued" : "draft");
        reference.put("preview_url", previewUrl(document.getId()));
        reference.put("pdf_url", downloadUrl(document.getId()));
        reference.put("created_at", document.getCreatedAt());
        return reference;
    }

    public String previewUrl(UUID documentId) {
        return "/api/documents/%s/preview".formatted(documentId);
    }

    public String downloadUrl(UUID documentId) {
        return "/api/documents/%s/download".formatted(documentId);
    }

    private Map<String, Object> mutableMap(Object value) {
        Map<String, Object> result = new LinkedHashMap<>();
        if (value instanceof Map<?, ?> source) {
            source.forEach((key, item) -> result.put(String.valueOf(key), item));
        }
        return result;
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
