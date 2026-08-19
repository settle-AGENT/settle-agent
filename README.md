# Settle Agent

국내 체류 외국인 금융 정착 AI Agent

## 시작하기

```bash
docker compose up -d

cd backend
./gradlew bootRun
```

상태 확인: http://localhost:8080/actuator/health

## 구조

- `backend/src/`       Spring Boot API 및 PostgreSQL 영속성 계층 (FS-2)
- `ai/`                LangGraph 에이전트와 AI 처리 (AI-1, AI-2)
- `frontend/`          Next.js (FS-1)
- `mock-institution/`  기관 API 시뮬레이터 (Cloud-2)
- `infra/`             배포 (Cloud-1)
