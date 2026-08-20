package com.settle.backend.domain.document.entity;

public enum GeneratedDocumentStatus {
    GENERATING,
    READY, // 미리보기까지 작성된 초안(기존 데이터 호환 이름)
    ISSUED,
    FAILED
}
