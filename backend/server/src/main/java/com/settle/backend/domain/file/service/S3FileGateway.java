package com.settle.backend.domain.file.service;

import java.time.Duration;

public interface S3FileGateway {
    String createPngUploadUrl(String objectKey, Duration duration);

    void uploadPdf(String objectKey, byte[] bytes);

    StoredFile download(String objectKey);

    record StoredFile(String contentType, byte[] bytes) {
    }
}
