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

1. `POST /api/v1/files/presigned-uploads`로 S3 업로드 URL을 발급받습니다.
2. 클라이언트가 외국인등록증 또는 여권 사진을 S3에 직접 업로드합니다.
3. `POST /api/v1/documents/extractions`에 object key와 문서 종류를 전달합니다.
4. 백엔드가 AI 서버에 추출을 요청하고 반환 JSON과 원본 object key를 저장합니다.

회원 인증은 PostgreSQL과 연결되며 JWT를 발급합니다. S3·AI 서버 연동은 환경 설정이 필요합니다.
