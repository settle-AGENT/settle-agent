package com.settle.backend.domain.document.repository;

import com.settle.backend.domain.document.entity.IdentityDocument;
import java.util.List;
import java.util.UUID;

public interface DocumentRepository {

    IdentityDocument save(IdentityDocument document);

    List<IdentityDocument> findAllByMemberId(UUID memberId);
}
