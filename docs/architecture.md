# 기술 스택과 아키텍처

> 에이전트 설계는 [agent.md](agent.md), 검색은 [rag.md](rag.md), 서류와 개인정보는 [documents-and-privacy.md](documents-and-privacy.md)를 참고하세요.

## 기술 스택

**Frontend**

![React](https://img.shields.io/badge/React_18-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite_5-646CFF?style=for-the-badge&logo=vite&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-009639?style=for-the-badge&logo=nginx&logoColor=white)

**Backend**

![Java](https://img.shields.io/badge/Java_21-ED8B00?style=for-the-badge&logo=openjdk&logoColor=white)
![Spring Boot](https://img.shields.io/badge/Spring_Boot_3.4-6DB33F?style=for-the-badge&logo=springboot&logoColor=white)
![JPA](https://img.shields.io/badge/Spring_Data_JPA-6DB33F?style=for-the-badge&logo=spring&logoColor=white)
![JWT](https://img.shields.io/badge/JWT-000000?style=for-the-badge&logo=jsonwebtokens&logoColor=white)

**AI**

![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white)
![Claude](https://img.shields.io/badge/Claude_API-D97757?style=for-the-badge&logo=anthropic&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![CLOVA OCR](https://img.shields.io/badge/CLOVA_OCR-03C75A?style=for-the-badge&logo=naver&logoColor=white)

**Infra**

![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Caddy](https://img.shields.io/badge/Caddy_2-1F88C0?style=for-the-badge&logo=caddy&logoColor=white)
![AWS EC2](https://img.shields.io/badge/AWS_EC2-FF9900?style=for-the-badge&logo=amazonec2&logoColor=white)
![AWS S3](https://img.shields.io/badge/AWS_S3-569A31?style=for-the-badge&logo=amazons3&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white)

<br/>

## 아키텍처

```
                     ┌───────────────┐
브라우저 ──────────► │ Caddy (:8081) │  경로 라우팅
                     └───────┬───────┘
                  ┌──────────┼──────────┐
                  ▼          ▼          ▼
            frontend      backend    /health/*
          React + Vite  Spring Boot
            (nginx)     Java 21 · :8080
                            │  RestClient
                            ▼
                      ai · FastAPI + LangGraph · :8000
                            │
                            ▼
                      PostgreSQL + pgvector
```

| 서비스 | 스택 | 역할 | 포트 |
|---|---|---|---|
| `frontend/` | React 18 · Vite 5 · React Router | 모바일 프레임 단일 페이지. 촬영 → 확인 → 과제 → 서류 흐름 | 5173 (dev) / 3000 (nginx) |
| `backend/` | Java 21 · Spring Boot 3 · JPA | 회원·JWT 인증, S3 presigned 업로드, 생성 서류 영속화, AI 서비스 중계 | 8080 |
| `ai/` | Python 3.12 · FastAPI · LangGraph | 에이전트 상태 기계, OCR 추출, 룰 엔진, RAG 질의응답, 서식 렌더 | 8000 |
| `db` | pgvector/pgvector:pg16 | 회원·서류 테이블, LangGraph 체크포인트, `rag.chunk` 벡터 | 5432 |
| `deploy/` | Caddy 2 | 리버스 프록시 (`/api/*` → backend, 그 외 → frontend) | 8081 |
| `mock-institution/` | Python | 기관 API 시뮬레이터 (스켈레톤) | — |

프론트는 개발 시 Vite 프록시로 `/api/v1/*`를 Spring에, 나머지 `/api/*`를 AI에 직접 보냅니다. 운영에서는 Caddy가 `/api/*`를 전부 backend로 보내고 backend가 AI를 중계합니다.

