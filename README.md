# Settle Agent

국내 체류 외국인 금융 정착 AI Agent

## 시작하기

```bash
docker compose up -d

cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

API 스펙: http://localhost:8000/docs

## 구조

- `backend/app/agent/` LangGraph 에이전트 (AI-1)
- `backend/app/nodes/` Profiler / DocBuilder (AI-2)
- `backend/rules/`     체류자격·근거법령 룰 (AI-1)
- `backend/mappings/`  서식 필드 매핑 (AI-2)
- `backend/app/api/`   FastAPI 라우팅 (FS-2)
- `frontend/`          Next.js (FS-1)
- `mock-institution/`  기관 API 시뮬레이터 (Cloud-2)
- `infra/`             배포 (Cloud-1)
