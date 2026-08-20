package com.settle.backend.domain.file.service;

import com.settle.backend.domain.file.dto.PresignedUploadRequest;
import com.settle.backend.domain.file.dto.PresignedUploadResponse;
import com.settle.backend.domain.file.entity.UploadStatus;
import com.settle.backend.domain.file.entity.UploadTicket;
import com.settle.backend.domain.file.repository.UploadRepository;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class FileService {
    private static final String PNG_CONTENT_TYPE = "image/png";
    private static final byte[] PNG_SIGNATURE = {
            (byte) 0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a
    };
    private static final Duration UPLOAD_URL_TTL = Duration.ofMinutes(5);

    private final UploadRepository uploadRepository;
    private final S3FileGateway s3;

    public FileService(UploadRepository uploadRepository, S3FileGateway s3) {
        this.uploadRepository = uploadRepository;
        this.s3 = s3;
    }

    public PresignedUploadResponse issueUploadUrl(UUID memberId, PresignedUploadRequest request) {
        UUID uploadId = UUID.randomUUID();
        String objectKey = "members/%s/uploads/%s.png".formatted(memberId, uploadId);
        Instant expiresAt = Instant.now().plus(UPLOAD_URL_TTL);
        UploadTicket upload = new UploadTicket(
                uploadId,
                memberId,
                request.documentType(),
                objectKey,
                PNG_CONTENT_TYPE,
                UploadStatus.PENDING,
                expiresAt
        );
        String uploadUrl = s3.createPngUploadUrl(objectKey, UPLOAD_URL_TTL);
        uploadRepository.save(upload);
        return new PresignedUploadResponse(uploadId, uploadUrl, UPLOAD_URL_TTL.toSeconds());
    }

    public PreparedUpload prepareForExtraction(UUID memberId, UUID uploadId) {
        UploadTicket upload = uploadRepository.findById(uploadId)
                .filter(candidate -> candidate.memberId().equals(memberId))
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));

        if (upload.status() == UploadStatus.PROCESSING) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "upload_processing");
        }
        if (upload.status() == UploadStatus.DONE) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "upload_already_processed");
        }

        S3FileGateway.StoredFile stored;
        try {
            stored = s3.download(upload.objectKey());
        } catch (RuntimeException exception) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "upload_not_completed", exception);
        }
        upload = upload.withStatus(UploadStatus.UPLOADED);
        uploadRepository.save(upload);

        if (!PNG_CONTENT_TYPE.equalsIgnoreCase(stored.contentType()) || !isPng(stored.bytes())) {
            uploadRepository.save(upload.withStatus(UploadStatus.FAILED));
            throw new ResponseStatusException(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "unsupported_media_type");
        }

        uploadRepository.save(upload.withStatus(UploadStatus.PROCESSING));
        return new PreparedUpload(upload, stored.bytes());
    }

    public void markDone(UploadTicket upload) {
        uploadRepository.save(upload.withStatus(UploadStatus.DONE));
    }

    public void markFailed(UploadTicket upload) {
        uploadRepository.save(upload.withStatus(UploadStatus.FAILED));
    }

    private boolean isPng(byte[] bytes) {
        return bytes.length >= PNG_SIGNATURE.length
                && Arrays.equals(PNG_SIGNATURE, Arrays.copyOf(bytes, PNG_SIGNATURE.length));
    }

    public record PreparedUpload(UploadTicket ticket, byte[] bytes) {
    }
}
