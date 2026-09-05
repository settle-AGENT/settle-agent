# Settle Agent

국내 체류 외국인의 금융·행정 정착을 돕는 AI 에이전트.

신분증을 찍어 올리면 OCR 로 프로필을 만들고, 체류자격 룰로 **지금 무엇을 할 수 있고
무엇이 막혀 있는지**를 계산해 과제 목록으로 보여준다. 법령·안내매뉴얼을 검색해 근거와 함께
답하고, 통합신청서 같은 서식을 채워 PDF 로 만들어 준다. 되돌릴 수 없는 행동에는 승인 게이트가 걸린다.

```
외국인등록증·여권 촬영 → 프로필 확인 → 체류자격 판정 → 과제 그래프
                                              ↓
                            질의응답(법령·매뉴얼 RAG) · 서류 생성 → 승인 → 보관함
```

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

프론트는 개발 시 Vite 프록시로 `/api/v1/*` 를 Spring 에, 나머지 `/api/*` 를 AI 에 직접 보낸다.
운영에서는 Caddy 가 `/api/*` 를 전부 backend 로 보내고 backend 가 AI 를 중계한다.

## 빠른 시작

### 전체 스택 (Docker)

```bash
cp ai/.env.example .env.local
```

값을 채운 뒤(`ANTHROPIC_API_KEY`, `CLOVA_*` 등):

```bash
docker compose -f compose.local.yml up -d --build
```

- 앱 http://localhost:8081
- Swagger http://localhost:8081/swagger-ui.html
- 헬스체크 http://localhost:8081/health/ai · http://localhost:8081/health/backend

### 개별 실행 (개발)

```bash
docker compose up -d db
```

```bash
cd ai && cp .env.example .env && uv sync && uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd backend/server && cp .env.example .env && ./gradlew bootRun
```

```bash
cd frontend/frontend-react && npm install && npm run dev
```

API 스펙: AI http://localhost:8000/docs · Backend http://localhost:8080/swagger-ui.html

`JWT_SECRET` 은 32바이트 이상이어야 한다. 백엔드가 아직 없어도 프론트는 목데이터로 돈다 —
`VITE_USE_MOCK=true npm run dev`.

## 환경 변수

**ai** (`ai/.env.example`)

| 키 | 없으면 |
|---|---|
| `ANTHROPIC_API_KEY` | LLM 기능이 전부 꺼진다. 질의응답도, 응답·오류의 다국어 변환도 안 되고 화면이 항상 한국어로 나온다 |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` |
| `DATABASE_URL` | 벡터 검색이 죽고 BM25 단독으로 동작한다. 세션도 휘발된다 |
| `CLOVA_INVOKE_URL` / `CLOVA_SECRET_KEY` | 신분증 OCR 불가 |
| `RESEARCH_ENABLED` | 기본 `1`. `0` 이면 도구 루프를 끄고 단발 RAG 로 되돌린다 |

**backend** (`backend/server/.env.example`)

`DB_URL` · `DB_USERNAME` · `DB_PASSWORD` · `JWT_SECRET` · `JWT_ACCESS_TOKEN_TTL_SECONDS`
· `AWS_REGION` · `AWS_S3_BUCKET` · `AI_BASE_URL` · `AI_CONNECT_TIMEOUT_SECONDS` · `AI_READ_TIMEOUT_SECONDS`

**frontend** — `VITE_API_BASE_URL` (기본 `/api`), `VITE_USE_MOCK`

## 에이전트 설계

`ai/app/agent/graph.py` 는 **통제된 상태 기계**다. LLM 에게 자율적인 툴 선택권을 주지 않는다.

```
planner → router ─┬→ slot_filler          부족한 값 질문
                  ├→ doc_builder → approval_gate → executor → replanner
                  └→ explainer            설명·질의응답
```

- **경로가 파일에 고정**되어 있고, 승인 게이트를 우회하는 엣지가 존재하지 않는다.
  L2 액션은 LLM 이 어떻게 동작하든 사용자 승인 없이 실행될 수 없다.
- LLM 이 쓰이는 곳은 Router(의도 분류), Explainer(문장 생성), Researcher(조회 도구 루프)뿐.
  **무엇이 가능한지는 룰이 정한다.**
- Researcher 의 도구는 판단 재료가 아니라 **결론**을 돌려준다 — 매트릭스 원문을 넘기면
  모델이 체류자격을 추론하게 되므로, planner 가 이미 낸 결론(`status`, `blocked_by`)만 전달한다.
  모델은 틀린 말을 할 수는 있어도 틀린 행동은 하지 못한다.

### 위험 등급

| 등급 | 처리 |
|---|---|
| L1 | 자동 통과 |
| L2 | 사용자 승인 필요 — 승인 UI 를 띄우고 턴 종료 |
| L3 | 법적으로 대행 불가 — 실행하지 않고 안내만 (예: 금융실명법 제3조) |

### 룰

| 파일 | 내용 |
|---|---|
| `ai/rules/visa_matrix.yaml` | 체류자격별 가능 액션 · 선행조건 · 기한 · 지참서류 · 제출처 · 위험등급 |
| `ai/rules/visa_codes.yaml` | 유효 체류자격 코드 (D-2, D-4, D-8, D-10, E-7, E-9, F-2, F-4, F-5, F-6, H-2) |
| `ai/rules/evidence.yaml` | 근거 법령 조문 — 안내마다 인용된다 |
| `ai/mappings/*.yaml` | 서식 필드 매핑 (통합신청서, 계좌개설 신청서) |

액션: `alien_registration` · `mobile_subscription` · `open_bank_account` · `residence_change` · `work_activity`.
현재 매트릭스에 상세 정의가 채워진 자격은 D-2 다.

### 선행조건과 완료는 다른 질문이다

`satisfied_if` 는 "이 값이 프로필에 있으면 현실에서는 이미 끝난 일" 이라는 뜻이다.
외국인등록번호가 그렇다 — 등록을 마쳐야 나오는 번호이므로, 가지고 있다는 사실
자체가 등록을 마쳤다는 증거다. planner 는 이것을 두 집합으로 나눠 쓴다.

| 집합 | 답하는 질문 | 채우는 주체 |
|---|---|---|
| `prereq_satisfied` | 현실에서 이미 끝난 일인가 → 뒤따르는 과제를 연다 | `satisfied_if` · executor |
| `completed` | 앱이 서류를 만들어 승인까지 받았나 → `done` 으로 표시한다 | executor (서류가 있는 과제) |

둘을 겸하게 두면 등록증을 이미 가진 사람이 계좌를 열려고 할 때 필요도 없는
통합신청서부터 만들어야 한다. 은행이 묻는 것은 등록된 사람인지이지, 이 앱으로
통합신청서를 만들었는지가 아니다.

## 검색 (RAG)

두 코퍼스를 함께 검색하고, 검색된 근거 안에서만 LLM 이 답한다.

| 코퍼스 | 무엇 | 개수 |
|---|---|---|
| `ai/rules/corpus.json` | 법령 조문 (출입국관리법·시행령·금융실명법·특정금융정보법) | 397 |
| `ai/rules/manual.json` | 외국인체류 안내매뉴얼 (법무부, 2026. 8.) | 1,212 |

- 영문 질의는 먼저 **문서에 실제로 쓰인 낱말로** 옮긴다 (`part-time job` → `시간제취업 체류자격 외 활동`).
- BM25(한글 음절 바이그램) + pgvector 코사인을 RRF 로 합친다. DB 가 없으면 BM25 단독.
- 사용자 체류자격과 일치하는 매뉴얼 조각에 ×1.6, 다른 자격 전용에 ×0.45 가중치.
- 임베딩은 이미지 빌드 때 미리 계산해 굽는다. 컨테이너 기동은 upsert 만 하고 몇 초에 끝난다.
- 상태는 `/health` 의 `rag` 에 나온다. `ready: false` 면 벡터 검색이 죽어 있다는 뜻이고,
  프로덕션 배포는 이 값이 true 여야 통과한다.

코퍼스 구축·매뉴얼 파싱·검색 평가는 [ai/README.md](ai/README.md) 에 자세히 있다.

> 안내매뉴얼 원본 PDF(15MB)는 리포에 없다. [하이코리아](https://www.hikorea.go.kr) 자료실에서
> 받아 `ai/corpus/manual/` 에 두고 `build_manual.py` 를 돌린다. 결과물 `rules/manual.json` 은
> 커밋되어 있으므로 코퍼스를 다시 만들 때만 원본이 필요하다.

## 서류 생성

`ai/app/nodes/doc_builder.py` — **LLM 을 쓰지 않는다.** 값 생성은 전부 결정적 매핑이다.

```
profile + mappings/*.yaml → Jinja2 (templates/*.html) → WeasyPrint → PDF
```

- 렌더에는 마스킹하지 않은 평문 프로필을 쓴다 (서버 내부에서만 생성).
  마스킹은 **응답을 만들 때만** 적용되고 state 원본은 항상 평문이다.
  그래서 무엇을 얼마나 들고 있는지가 중요하다 — 아래 "개인정보" 절 참고.
- OCR 신뢰도 0.95 미만 필드는 서류와 화면 양쪽에 '확인요망'으로 표시된다.
- WeasyPrint 는 Pango/cairo 를 dlopen 한다. 시스템 라이브러리가 없으면 PDF 생성이
  조용히 실패하고 HTML 만 남는다 (`ai/Dockerfile` 참고).

## 개인정보

무엇을 들고 있고 언제 버리는지.

| 데이터 | 어디에 | 언제 사라지나 |
|---|---|---|
| 신분증 원본 사진 | S3 `members/{id}/uploads/` | **OCR 직후 즉시 삭제** (`FileService.discardOriginal`) |
| OCR 원문 | — | **저장하지 않는다.** 추출 함수 밖으로 나가지 않는다 |
| 프로필 · 대화 | 체크포인터 (Postgres) | 보관기간 스크립트로 정리 (아래) |
| 생성 서류 PDF | S3 `members/{id}/generated-documents/` | 남는다 — 서류함은 회원 자산이다 |
| 임시 렌더 결과 | `ai/output/*.html`, `*.pdf` | 아직 정리하지 않는다 |

- **응답에 예외 메시지를 싣지 않는다.** OCR·프로필 처리 중 난 예외에는 신분증에서
  읽은 값이 섞일 수 있다. 클라이언트에는 예외 **타입만** 나가고, 원인은 서버
  로그의 traceback 에만 남는다.
- 외국인등록번호는 응답에서 마스킹된다(`990101-*******`). state 원본은 평문이므로
  저장 매체 암호화가 따로 필요하다 — `deploy/aws-hardening.md`.

```bash
uv run python scripts/purge_stale_sessions.py                # 30일 이상 방치된 세션
uv run python scripts/purge_raw_texts.py                     # 옛 체크포인트의 OCR 원문 (1회)
```

둘 다 기본이 dry-run 이다. `--apply` 를 붙여야 실제로 지운다.

세션 보관기간은 **마지막 활동 기준 30일**이다. 생성 기준이 아니라 활동 기준인
이유는, 90일 기한을 추적하는 앱에서 나이만으로 지우면 계속 쓰는 사람의 D-day 가
매번 리셋되기 때문이다.

AWS 쪽에서 해야 하는 것(버킷 기본 암호화, 퍼블릭 차단, EBS 암호화)은
[deploy/aws-hardening.md](deploy/aws-hardening.md) 에 모아 두었다.

## 주요 엔드포인트

**AI** (`ai/app/main.py`)

| 메서드 | 경로 | |
|---|---|---|
| GET | `/health` | `persistent`, `rag` 상태 포함 |
| POST | `/api/session` | 세션 생성·이어받기·리셋 |
| POST | `/api/profile/extract-upload` | 신분증 업로드 → OCR → 프로필 |
| POST | `/api/profile/confirm` | 확인 화면에서 고친 값 반영 |
| POST | `/api/chat` · `/api/chat/stream` | 대화 (스트림은 SSE 로 진행 단계 전송) |
| POST | `/api/actions/{id}/start` · `/preview` · `/approve` | 액션 시작 · 서류 생성 · 승인 |
| GET | `/api/state` · `/api/ledger` | 새로고침 복원 · 처리 이력 |
| GET | `/api/documents/{id}/preview` · `/api/documents/{id}.pdf` | 생성 서류 |

**Backend**

| 메서드 | 경로 | |
|---|---|---|
| POST | `/api/v1/auth/signup` · `/api/v1/auth/login` | JWT 발급 |
| POST | `/api/v1/uploads` | S3 presigned PUT URL |
| POST | `/api/v1/documents/extractions` | `uploadId` 로 OCR 중계 |
| POST | `/api/session` · `/api/chat` · `/api/chat/stream` · `/api/actions/{id}/start` | AI 중계 |
| POST | `/api/actions/{id}/preview` · `/api/actions/{id}/approve` | 서류 생성 후 영속화 |
| GET | `/api/ledger` · `/api/documents/{id}/preview` · `/api/documents/{id}/download` | |

모든 에이전트 응답은 `{ schema_version, reply, ui, state }` 봉투다.
오류는 `{ detail: { error, message, details } }`.
계약은 `ai/app/api/schemas.py` 에 있고 **필드 추가만 허용, 삭제·개명 금지**다.

## 테스트

```bash
cd ai && uv run pytest
```

```bash
cd backend/server && ./gradlew test
```

검색이 정상인지 확인:

```bash
cd ai && DATABASE_URL=postgresql://settle:settle@localhost:5432/settle uv run python eval/retrieval_check.py
```

정답 문서를 하나로 특정하기는 어려우므로, 무너지면 반드시 깨지는 것만 본다 —
내 자격 문서가 남의 자격 문서에 밀리지 않는가.

## 디렉터리

```
ai/
  app/agent/       LangGraph 상태 기계 (graph · service · state)
  app/nodes/       planner · profiler · doc_builder · qa · researcher
  app/extractors/  외국인등록증 · 여권 OCR (CLOVA)
  app/tools/       llm · embed · rag_store · progress
  rules/           체류자격 매트릭스 · 근거법령 · 코퍼스
  mappings/        서식 필드 매핑
  templates/       서식 HTML
  scripts/         코퍼스 구축 · 임베딩 · 적재 · 보관기간 정리
backend/server/    Spring Boot — domain: auth · member · file · document · agent · action · profile · card · application
frontend/frontend-react/
                   React + Vite (App.jsx 단일 스텝 라우팅)
deploy/            Caddyfile · 배포 스크립트 · IAM·CORS 정책 · AWS 보안 설정 안내
mock-institution/  기관 API 시뮬레이터
seed/              샘플 신분증 이미지 · 프로필
```

## CI/CD

- **CI** (`.github/workflows/ci-cd.yml`) — `develop`·`master` 대상 PR 에서 실행.
  변경된 서비스만 빌드하고, AI 는 `pytest` 를 돌린 뒤 컨테이너를 띄워 `/health`
  스모크 테스트까지 한다. `CodeRabbit` 이 같은 PR 에 리뷰를 단다(`.coderabbit.yaml`).
- **브랜치 정책** — `master` 로는 동일 저장소의 `develop` 브랜치만 PR 을 보낼 수 있다.
  기본 작업 브랜치는 `develop`, `master` 는 릴리스 브랜치다.
- **CD** (`cd-production.yml`) — `master` push 시 이미지 3개를 GHCR 에 올리고,
  SSM 으로 EC2 에 `compose.selfhost.yml`·`Caddyfile`·`deploy/remote-deploy.sh` 를
  실어 보내 pull·기동시킨다. 인스턴스에서 빌드하지 않는다.
  배포 검증은 인스턴스 내부와 **공인 DNS 양쪽**에서 한다 — 내부 `--resolve` 만으로는
  외부 접속을 증명하지 못한다.
- **롤백** — `workflow_dispatch` 에 이전 커밋 SHA 를 `image_tag` 로 넣으면
  빌드를 건너뛰고 그 이미지로 되돌린다.

배포 인프라는 EC2 한 대다. Postgres(pgvector)도 같은 박스의 컨테이너로 돌고,
매니지드 의존은 S3 하나뿐이다. 자세한 것은 `compose.selfhost.yml` 주석 참고.

Postgres 가 EC2 위의 컨테이너이므로 저장 암호화는 RDS 설정이 아니라 **EBS 볼륨
암호화**다. 기존 볼륨에는 제자리 적용이 안 되고 스냅샷 교체가 필요하다 —
절차와 남은 항목은 [deploy/aws-hardening.md](deploy/aws-hardening.md) 에 있다.
