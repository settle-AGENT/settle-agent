package com.settle.backend.domain.document.repository;

import com.settle.backend.domain.document.entity.GeneratedDocument;
import com.settle.backend.domain.document.entity.GeneratedDocumentStatus;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface GeneratedDocumentRepository extends JpaRepository<GeneratedDocument, UUID> {

    Optional<GeneratedDocument> findByIdAndMember_Id(UUID documentId, UUID memberId);

    List<GeneratedDocument> findAllByMember_IdAndSessionIdAndStatusOrderByCreatedAtDesc(
            UUID memberId,
            String sessionId,
            GeneratedDocumentStatus status
    );

}
