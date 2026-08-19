package com.settle.backend.domain.file.service;

import com.settle.backend.common.exception.FeatureNotConfiguredException;
import com.settle.backend.domain.file.dto.PresignedUploadRequest;
import com.settle.backend.domain.file.dto.PresignedUploadResponse;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class FileService {

    public PresignedUploadResponse issueUploadUrl(UUID memberId, PresignedUploadRequest request) {
        throw new FeatureNotConfiguredException("S3 presigned URL 발급 구현이 아직 연결되지 않았습니다.");
    }
}
