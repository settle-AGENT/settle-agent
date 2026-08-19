package com.settle.backend.domain.file.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.settle.backend.domain.file.dto.PresignedUploadRequest;
import com.settle.backend.domain.file.dto.PresignedUploadResponse;
import com.settle.backend.domain.file.entity.DocumentType;
import com.settle.backend.domain.file.entity.UploadStatus;
import com.settle.backend.domain.file.repository.InMemoryUploadRepository;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class FileServiceTest {
    private static final UUID MEMBER_ID = UUID.randomUUID();
    private static final byte[] PNG = {
            (byte) 0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00
    };

    @Test
    void preparesValidPngForExtraction() {
        FakeS3 gateway = new FakeS3(new S3FileGateway.StoredFile("image/png", PNG));
        FileService service = new FileService(new InMemoryUploadRepository(), gateway);
        PresignedUploadResponse upload = service.issueUploadUrl(
                MEMBER_ID, new PresignedUploadRequest(DocumentType.arc_front)
        );

        FileService.PreparedUpload prepared = service.prepareForExtraction(MEMBER_ID, upload.uploadId());

        assertThat(prepared.ticket().documentType()).isEqualTo(DocumentType.arc_front);
        assertThat(prepared.bytes()).isEqualTo(PNG);
        service.markDone(prepared.ticket());
        assertThat(prepared.ticket().withStatus(UploadStatus.DONE).status()).isEqualTo(UploadStatus.DONE);
    }

    @Test
    void rejectsFileWhoseBytesAreNotPng() {
        FakeS3 gateway = new FakeS3(new S3FileGateway.StoredFile("image/png", "not-png".getBytes()));
        FileService service = new FileService(new InMemoryUploadRepository(), gateway);
        PresignedUploadResponse upload = service.issueUploadUrl(
                MEMBER_ID, new PresignedUploadRequest(DocumentType.passport)
        );

        assertThatThrownBy(() -> service.prepareForExtraction(MEMBER_ID, upload.uploadId()))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("415 UNSUPPORTED_MEDIA_TYPE");
    }

    private static final class FakeS3 implements S3FileGateway {
        private final StoredFile storedFile;

        private FakeS3(StoredFile storedFile) {
            this.storedFile = storedFile;
        }

        @Override
        public String createPngUploadUrl(String objectKey, Duration duration) {
            return "https://s3.example.test/upload";
        }

        @Override
        public void uploadPdf(String objectKey, byte[] bytes) {
        }

        @Override
        public StoredFile download(String objectKey) {
            return storedFile;
        }
    }
}
