# Settle Agent Backend

Drizzle SQLite 스키마의 네 모델을 PostgreSQL 기반 Spring Boot 영속성 계층으로 구현한 모듈입니다. AI 테이블과 분리하기 위해 모든 업무 테이블은 `app` 스키마에 생성합니다.

## 기술 구성

- Java 21 / Spring Boot 3.5
- Spring Data JPA
- PostgreSQL / Flyway
- Gradle Wrapper

## 로컬 실행

루트에서 PostgreSQL을 실행한 다음 백엔드를 시작합니다.

```bash
docker compose up -d db

cd backend
./gradlew bootRun
```

기본 접속값은 `jdbc:postgresql://localhost:5432/settle`, 사용자명과 비밀번호는 모두 `settle`입니다. 다른 DB를 쓸 때는 다음 환경변수를 설정하세요.

```bash
export DB_URL='jdbc:postgresql://localhost:5432/settle'
export DB_USERNAME='settle'
export DB_PASSWORD='settle'
```

애플리케이션 시작 시 Flyway가 `app` 스키마 안에 `users`, `cards`, `account_opening_applications`, `integrated_applications`와 관련 인덱스 및 외래 키를 생성합니다.

## 테스트

```bash
./gradlew test
```

테스트는 H2 격리 DB에서 JPA 매핑, 유니크 제약조건, `account_purposes` JSON 변환을 검증합니다.

> `password_hash`, 등록번호, 여권번호 및 이미지 URL은 이미 해시 또는 암호화된 값만 전달한다는 저장 계약을 전제로 합니다.
