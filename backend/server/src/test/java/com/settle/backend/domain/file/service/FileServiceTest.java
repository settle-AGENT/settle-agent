package com.settle.backend.domain.file.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.settle.backend.domain.file.dto.PresignedUploadRequest;
import com.settle.backend.domain.file.dto.PresignedUploadResponse;
import com.settle.backend.domain.file.entity.DocumentType;
import com.settle.backend.domain.file.entity.UploadStatus;
import com.settle.backend.domain.file.repository.InMemoryUploadRepository;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
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

    @Test
    void deletesTheOriginalWhenTheUploadIsNotAPng() {
        // 형식이 틀렸어도 올라온 것은 신분증 사진일 수 있다. 이 티켓은 FAILED 라
        // 다시 쓰이지 않으므로, 여기서 안 지우면 원본이 영영 남는다.
        FakeS3 gateway = new FakeS3(new S3FileGateway.StoredFile("image/png", "not-png".getBytes()));
        FileService service = new FileService(new InMemoryUploadRepository(), gateway);
        PresignedUploadResponse upload = service.issueUploadUrl(
                MEMBER_ID, new PresignedUploadRequest(DocumentType.arc_front)
        );

        assertThatThrownBy(() -> service.prepareForExtraction(MEMBER_ID, upload.uploadId()))
                .isInstanceOf(ResponseStatusException.class);

        assertThat(gateway.deleted).hasSize(1);
        assertThat(gateway.deleted.get(0)).contains("/uploads/");
    }

    @Test
    void rejectsAnotherMembersUploadAsNotFound() {
        FakeS3 gateway = new FakeS3(new S3FileGateway.StoredFile("image/png", PNG));
        FileService service = new FileService(new InMemoryUploadRepository(), gateway);
        PresignedUploadResponse upload = service.issueUploadUrl(
                MEMBER_ID, new PresignedUploadRequest(DocumentType.arc_back)
        );

        assertThatThrownBy(() -> service.prepareForExtraction(UUID.randomUUID(), upload.uploadId()))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("404 NOT_FOUND");
    }

    @Test
    void deletesTheIdPhotoOnceExtractionSucceeds() {
        FakeS3 gateway = new FakeS3(new S3FileGateway.StoredFile("image/png", PNG));
        FileService service = new FileService(new InMemoryUploadRepository(), gateway);
        PresignedUploadResponse upload = service.issueUploadUrl(
                MEMBER_ID, new PresignedUploadRequest(DocumentType.arc_front)
        );
        FileService.PreparedUpload prepared = service.prepareForExtraction(MEMBER_ID, upload.uploadId());

        service.markDone(prepared.ticket());

        assertThat(gateway.deleted).containsExactly(prepared.ticket().objectKey());
    }

    @Test
    void deletesTheIdPhotoEvenWhenExtractionFails() {
        FakeS3 gateway = new FakeS3(new S3FileGateway.StoredFile("image/png", PNG));
        FileService service = new FileService(new InMemoryUploadRepository(), gateway);
        PresignedUploadResponse upload = service.issueUploadUrl(
                MEMBER_ID, new PresignedUploadRequest(DocumentType.passport)
        );
        FileService.PreparedUpload prepared = service.prepareForExtraction(MEMBER_ID, upload.uploadId());

        service.markFailed(prepared.ticket());

        assertThat(gateway.deleted).containsExactly(prepared.ticket().objectKey());
    }

    @Test
    void keepsTheRequestSuccessfulWhenTheDeleteFails() {
        // 추출은 이미 끝났다. 정리에 실패했다고 성공한 요청을 뒤집지 않는다.
        FakeS3 gateway = new FakeS3(new S3FileGateway.StoredFile("image/png", PNG));
        gateway.deleteFails = true;
        FileService service = new FileService(new InMemoryUploadRepository(), gateway);
        PresignedUploadResponse upload = service.issueUploadUrl(
                MEMBER_ID, new PresignedUploadRequest(DocumentType.arc_back)
        );
        FileService.PreparedUpload prepared = service.prepareForExtraction(MEMBER_ID, upload.uploadId());

        service.markDone(prepared.ticket());

        assertThat(gateway.deleted).isEmpty();
    }

    private static final class FakeS3 implements S3FileGateway {
        private final StoredFile storedFile;
        private final List<String> deleted = new ArrayList<>();
        private boolean deleteFails;

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

        @Override
        public void delete(String objectKey) {
            if (deleteFails) {
                throw new IllegalStateException("s3 unavailable");
            }
            deleted.add(objectKey);
        }
    }
}
