package com.settle.backend.domain.file.service;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

@Component
public class AwsS3FileGateway implements S3FileGateway {
    private static final String PNG_CONTENT_TYPE = "image/png";

    private final S3Client s3Client;
    private final S3Presigner presigner;
    private final String bucket;

    public AwsS3FileGateway(
            S3Client s3Client,
            S3Presigner presigner,
            @Value("${settle.aws.s3-bucket}") String bucket
    ) {
        this.s3Client = s3Client;
        this.presigner = presigner;
        this.bucket = bucket;
    }

    @Override
    public String createPngUploadUrl(String objectKey, Duration duration) {
        requireBucket();
        PutObjectRequest put = PutObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .contentType(PNG_CONTENT_TYPE)
                .build();
        return presigner.presignPutObject(PutObjectPresignRequest.builder()
                        .signatureDuration(duration)
                        .putObjectRequest(put)
                        .build())
                .url()
                .toString();
    }

    @Override
    public StoredFile download(String objectKey) {
        requireBucket();
        ResponseBytes<GetObjectResponse> object = s3Client.getObjectAsBytes(
                GetObjectRequest.builder().bucket(bucket).key(objectKey).build()
        );
        return new StoredFile(object.response().contentType(), object.asByteArray());
    }

    private void requireBucket() {
        if (bucket == null || bucket.isBlank()) {
            throw new IllegalStateException("AWS_S3_BUCKET 환경변수가 필요합니다.");
        }
    }
}
