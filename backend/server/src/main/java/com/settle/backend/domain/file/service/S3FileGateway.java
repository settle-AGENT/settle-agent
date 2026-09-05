package com.settle.backend.domain.file.service;

import java.time.Duration;

public interface S3FileGateway {
    String createPngUploadUrl(String objectKey, Duration duration);

    void uploadPdf(String objectKey, byte[] bytes);

    StoredFile download(String objectKey);

    /** 객체를 지운다. 없는 키를 지워도 성공으로 본다(S3 의 DELETE 는 멱등하다). */
    void delete(String objectKey);

    record StoredFile(String contentType, byte[] bytes) {
    }
}
