// 백엔드(Spring Boot) API 클라이언트.
// 엔드포인트가 아직 없으면 자동으로 목데이터로 폴백한다(MOCK=true).
// 실제 API가 준비되면 MOCK=false 로 바꾸거나 VITE_USE_MOCK=false 로 실행.

const MOCK = import.meta.env.VITE_USE_MOCK !== "false";

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

// ── 목데이터: seed/ocr_cache 의 실제 인물(NGUYEN VAN A) 기준 ──────────
const MOCK_EXTRACT = {
  profile: {
    name_en: "NGUYEN THI MAI",
    arc_no: "031120-6123456",
    nationality: "IDN",
    visa_type: "D-2-2",
    stay_expiry: "2028.02.27",
    addr_kr: "서울 성북구 안암로 145, 국제학사 B-412",
    birth_date: "2003.11.20",
    sex: "F",
  },
  // confidence < 0.9 → 사용자 확인 대상 (arc.py 규약)
  confidence: {
    name_en: 0.99,
    arc_no: 0.97,
    nationality: 0.96,
    visa_type: 0.96,
    stay_expiry: 0.64, // 만료일 흐릿 → 확인 필요
    addr_kr: 0.94,
    birth_date: 0.97,
  },
  dropped: [],
  missing_sides: [],
};

const NATIONALITY_LABEL = {
  VNM: "베트남", CHN: "중국", MNG: "몽골", UZB: "우즈베키스탄",
  NPL: "네팔", IDN: "인도네시아", JPN: "일본", USA: "미국",
};

// ── API ─────────────────────────────────────────────────────────────
// 1) 외국인등록증/여권 OCR 추출
export async function extractDocs({ arcFront, arcBack, passport }) {
  if (MOCK) return delay(MOCK_EXTRACT);
  return post("/api/ocr/extract", { arcFront, arcBack, passport });
}

// 2) 프로필 확정 + 추가 답변 저장
export async function saveProfile(profile, answers) {
  if (MOCK) return delay({ profileId: "mock-" + Date.now(), profile, answers });
  return post("/api/profile", { profile, answers });
}

// 3) 룰 엔진 판정
export async function getVerdict(profileId, answers) {
  if (MOCK) return delay(mockVerdict(answers));
  return post("/api/verdict", { profileId, answers });
}

// 4) 서류 생성(계좌개설신청서 + 통합 신청서)
export async function buildDocuments(profileId) {
  if (MOCK) return delay(MOCK_DOCS);
  return post("/api/documents", { profileId });
}

export function nationalityLabel(code) {
  return NATIONALITY_LABEL[code] || code;
}

// ── 판정 룰(프론트 목). 실제 판정은 백엔드 rules 엔진이 담당 ──────────
function mockVerdict(answers = {}) {
  const passportIssue = answers.scenario === "passport" || answers.passportIssue === true;
  const noPhone = answers.phone === "no";
  const noCert = answers.cert === "no";
  const kind = passportIssue ? "passport" : noPhone ? "phone" : noCert ? "cert" : "ready";
  const sources = [
    "금융거래 실명확인 업무 가이드 — 외국인 확인서류 §3.2",
    "한도제한계좌 해제 요건 안내 (2026.01 개정)",
    "대상 은행: KB국민은행 유학생 계좌개설 기준",
  ];
  if (kind === "passport")
    return {
      kind, sources,
      headline: "서류 1건을 확인해야 해요",
      summary: "여권 만료가 4개월 남았어요. 은행은 최소 6개월 유효한 여권을 요구하니 방문 전에 재발급하세요.",
      blocker: { title: "여권 유효기간", meta: "여권 유효기간 · VLM 추출값", badge: "추출값",
        body: "여권에서 읽음: 만료 2026.12.09 — 6개월 기준 미달. 외국인등록증 정보는 문제없어요." },
      limited: { status: "재발급 후", ready: false, body: "나머지는 모두 통과했어요. 여권만 재발급하면 두 계좌 모두 가능해요." },
      regular: { status: "아직", body: "6개월 이상 체류 기록이나 소득 증빙이 필요해요. 대부분 한도제한계좌로 시작해 나중에 승격해요." },
    };
  if (kind === "phone")
    return {
      kind, sources,
      headline: "아직 준비 전 — 1가지만 해결하면 돼요",
      summary: "은행 방문 전에 본인 명의 국내 휴대폰이 필요해요. 나머지는 모두 준비됐어요.",
      blocker: { title: "본인 명의 휴대폰", badge: "필수",
        body: "창구에서 문자로 본인확인을 해요. 친구 명의 번호는 거절돼요. 선불폰도 괜찮아요." },
      limited: { status: "휴대폰 개통 후", ready: false, body: "외국인등록증·여권·재학증명서는 준비됐어요. 휴대폰만 추가하면 방문할 수 있어요." },
      regular: { status: "아직", body: "6개월 이상 체류 기록이나 소득 증빙이 필요해요. 대부분 한도제한계좌로 시작해 나중에 승격해요." },
    };
  if (kind === "cert")
    return {
      kind, sources,
      headline: "거의 다 됐어요 — 서류 1건만 떼세요",
      summary: "재학증명서 또는 입학허가서가 아직 필요해요. 촬영은 안 해도 돼요 — 종이만 챙기세요.",
      blocker: { title: "재학증명서", badge: "종이만",
        body: "이 서류는 읽지 않아요. 학교 포털에서 인쇄해 창구에 제출하세요." },
      limited: { status: "서류 발급 후", ready: false, body: "외국인등록증·여권·휴대폰은 모두 통과했어요. 학교 서류만 남았어요." },
      regular: { status: "아직", body: "6개월 이상 체류 기록이나 소득 증빙이 필요해요. 대부분 한도제한계좌로 시작해 나중에 승격해요." },
    };
  return {
    kind, sources,
    headline: "오늘 은행에 가도 돼요",
    summary: "지금 가진 것으로 한도제한계좌를 만들 수 있어요. 6개월 후 한도를 올릴 수 있어요.",
    blocker: null,
    limited: { status: "준비됨", ready: true, body: "외국인등록증·여권·재학증명서·본인 명의 휴대폰만 있으면 충분해요." },
    regular: { status: "아직", body: "6개월 이상 체류 기록이나 소득 증빙이 필요해요. 대부분 한도제한계좌로 시작해 나중에 승격해요." },
  };
}

const MOCK_DOCS = {
  documents: [
    { id: "account_opening", title: "계좌개설신청서", subtitle: "계좌개설신청서 · KB국민은행",
      pages: 2, filled: 12, total: 12, expiresInDays: 7 },
    { id: "unified", title: "통합 신청서", subtitle: "통합 신청서 · 국가별 양식",
      pages: 1, filled: 9, total: 11, expiresInDays: 5 },
  ],
};

function delay(v, ms = 500) {
  return new Promise((r) => setTimeout(() => r(v), ms));
}
