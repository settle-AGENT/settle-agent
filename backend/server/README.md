# Settle Backend

Java 21 / Spring Boot 3 기반 API 서버입니다. `../app/`은 별도의 Python AI 코드 영역이며 Spring Boot에서 사용하지 않습니다.

## 실행

```bash
./gradlew bootRun
```

Swagger UI: http://localhost:8080/swagger-ui.html

## 패키지 구조

```text
src/main/java/com/settle/backend
├── common
│   ├── exception
│   └── health
└── domain
    ├── auth
    ├── member
    ├── file
    └── document
```

## 문서 처리 흐름

1. Bearer 토큰으로 `POST /api/v1/uploads`를 호출해 `uploadId`와 presigned PUT URL을 발급받습니다.
2. 클라이언트가 URL에 `Content-Type: image/png`으로 PNG를 PUT합니다.
3. `POST /api/v1/documents/extractions`에 `uploadId`만 전달합니다.
4. 백엔드가 S3 Content-Type과 PNG 시그니처를 검증하고 AI OCR 응답을 중계합니다.

S3 버킷 CORS에는 프론트엔드 Origin, `PUT` method, `Content-Type` header를 허용해야 합니다. 예:

```json
[
  {
    "AllowedOrigins": ["https://your-frontend.example.com"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["Content-Type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

회원 인증은 PostgreSQL과 연결되며 JWT를 발급합니다. S3·AI 서버 연동은 환경 설정이 필요합니다.
