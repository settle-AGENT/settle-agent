package com.settle.backend.domain.file.service;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.ResponseBytes;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.ServerSideEncryption;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

@Component
public class AwsS3FileGateway implements S3FileGateway {
    private static final String PNG_CONTENT_TYPE = "image/png";
    private static final String PDF_CONTENT_TYPE = "application/pdf";

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
    public void uploadPdf(String objectKey, byte[] bytes) {
        requireBucket();
        // 서버측 암호화를 요청에 명시한다. 버킷 기본 암호화가 켜져 있으면 어차피
        // 걸리지만, 그 설정에만 기대면 콘솔에서 꺼지는 순간 조용히 평문이 된다.
        //
        // presign 경로(createPngUploadUrl)에는 붙이지 않는다. presign 에 SSE 를
        // 넣으면 업로드하는 쪽이 x-amz-server-side-encryption 헤더를 똑같이
        // 보내야 서명이 맞는다. 프론트는 Content-Type 만 보내므로 업로드가 깨진다.
        // 그쪽은 버킷 기본 암호화로 덮는다 — deploy/aws-hardening.md 참고.
        PutObjectRequest put = PutObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .contentType(PDF_CONTENT_TYPE)
                .serverSideEncryption(ServerSideEncryption.AES256)
                .build();
        s3Client.putObject(put, RequestBody.fromBytes(bytes));
    }

    @Override
    public StoredFile download(String objectKey) {
        requireBucket();
        ResponseBytes<GetObjectResponse> object = s3Client.getObjectAsBytes(
                GetObjectRequest.builder().bucket(bucket).key(objectKey).build()
        );
        return new StoredFile(object.response().contentType(), object.asByteArray());
    }

    @Override
    public void delete(String objectKey) {
        requireBucket();
        s3Client.deleteObject(DeleteObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .build());
    }

    private void requireBucket() {
        if (bucket == null || bucket.isBlank()) {
            throw new IllegalStateException("AWS_S3_BUCKET 환경변수가 필요합니다.");
        }
    }
}
