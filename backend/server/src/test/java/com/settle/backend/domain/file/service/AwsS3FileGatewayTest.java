package com.settle.backend.domain.file.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

import java.io.IOException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@ExtendWith(MockitoExtension.class)
class AwsS3FileGatewayTest {

    @Mock
    private S3Client s3Client;

    @Mock
    private S3Presigner presigner;

    @Test
    void uploadsPdfWithExpectedS3Request() throws IOException {
        AwsS3FileGateway gateway = new AwsS3FileGateway(s3Client, presigner, "test-bucket");
        byte[] pdf = "%PDF-1.7 test".getBytes();

        gateway.uploadPdf("members/member-1/generated-documents/document-1.pdf", pdf);

        ArgumentCaptor<PutObjectRequest> requestCaptor = ArgumentCaptor.forClass(PutObjectRequest.class);
        ArgumentCaptor<RequestBody> bodyCaptor = ArgumentCaptor.forClass(RequestBody.class);
        verify(s3Client).putObject(requestCaptor.capture(), bodyCaptor.capture());

        PutObjectRequest request = requestCaptor.getValue();
        assertThat(request.bucket()).isEqualTo("test-bucket");
        assertThat(request.key()).isEqualTo("members/member-1/generated-documents/document-1.pdf");
        assertThat(request.contentType()).isEqualTo("application/pdf");
        try (var stream = bodyCaptor.getValue().contentStreamProvider().newStream()) {
            assertThat(stream.readAllBytes()).isEqualTo(pdf);
        }
    }
}
