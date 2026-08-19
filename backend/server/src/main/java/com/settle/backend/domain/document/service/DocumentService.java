package com.settle.backend.domain.document.service;

import com.settle.backend.common.exception.FeatureNotConfiguredException;
import com.settle.backend.domain.document.dto.ExtractDocumentRequest;
import com.settle.backend.domain.document.dto.ExtractDocumentResponse;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    public ExtractDocumentResponse extractAndSave(UUID memberId, ExtractDocumentRequest request) {
        throw new FeatureNotConfiguredException("AI 서버 클라이언트와 문서 저장소가 아직 연결되지 않았습니다.");
    }
}
