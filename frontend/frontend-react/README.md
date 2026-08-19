# settle-agent 프론트엔드 (React + Vite, JavaScript)

지금 프로토타입을 실제 실행 가능한 React 앱으로 옮긴 것입니다. 백엔드(Java + Spring Boot)에는 `/api/*`로 붙습니다.

## 실행

```bash
cd frontend-react
npm install
npm run dev          # http://localhost:5173  (백엔드 :8000 로 /api 프록시)
```

백엔드 API가 아직 없으면 자동으로 목데이터로 동작합니다(`src/api.js`의 `MOCK`). 실제 API가 준비되면:

```bash
VITE_USE_MOCK=false npm run dev
```

## 빌드 · 배포

```bash
npm run build        # dist/ 생성 → 기존 frontend/nginx.conf 로 정적 서빙
```

## 구조

- `src/App.jsx` — 화면 흐름 전체(로고→언어·비자·국적→촬영→프로필→질문→판정→준비→신청서→보관함→PDF), `useState` 단일 스텝 라우팅
- `src/api.js` — 백엔드 계약 + 목데이터. 엔드포인트: `POST /api/ocr/extract`, `POST /api/profile`, `POST /api/verdict`, `POST /api/documents`
- `src/components.jsx` — BridgeMark 로고, TopBar, Rail(진행 표시), Field(신뢰도 표시), PrimaryButton
- `src/styles.css` — 모바일 프레임 + 토큰

## 백엔드 계약 (프론트가 기대하는 형태)

`POST /api/ocr/extract` → `{ profile, confidence, dropped, missing_sides }`
- profile: `name_en, arc_no, nationality(ISO3), visa_type, stay_expiry, addr_kr, birth_date, sex`
- confidence: 필드별 0~1, **< 0.9 이면 프론트가 사용자 확인을 강제**
- `backend/app/extractors/arc.py` 반환 규약과 동일

`POST /api/verdict` → `{ kind, headline, blocker, limited, regular, sources[] }`
- 실제 판정은 백엔드 rules 엔진(`backend/rules/`)이 담당. 프론트 목은 참고용.

## 이 환경 제약
- 여기서는 GitHub 브랜치 생성·푸시·PR이 불가합니다. `frontend-react/`를 내려받아 로컬 `settle-agent/frontend/`에 넣고, 본인 계정으로 브랜치·커밋·PR 하세요.
