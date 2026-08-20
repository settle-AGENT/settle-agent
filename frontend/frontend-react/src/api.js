// 백엔드(Spring Boot) API 클라이언트.
// 목 모드가 필요한 경우에만 VITE_USE_MOCK=true로 실행한다.

const MOCK = import.meta.env.VITE_USE_MOCK === "true";

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

// ── AgentResponse 공통 계층 ─────────────────────────────────────────
// 모든 에이전트 엔드포인트는 { schema_version, reply, ui, state } 봉투로 답한다.
// 오류는 { detail: { error, message, details } } 다.
export const SCHEMA_VERSION = "1";

// ── 액세스 토큰 ──────────────────────────────────────────────────────
// Spring 의 모든 보호 엔드포인트가 Bearer 토큰에서 memberId 를 꺼낸다.
// S3 presigned PUT 에는 절대 붙이지 않는다 — 서명이 깨진다.
const TOKEN_KEY = "settle_access_token";

export function readToken() {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function saveToken(token) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(extra) {
  const token = readToken();
  return { ...extra, ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

export class AgentError extends Error {
  constructor(message, { status, code, details } = {}) {
    super(message);
    this.name = "AgentError";
    this.status = status;
    this.code = code;
    this.details = details || {};
  }
}

const ERROR_MESSAGE = {
  invalid_or_missing_token: "로그인이 만료됐어요. 다시 로그인해 주세요.",
  session_access_denied: "다른 계정의 세션이에요. 다시 로그인해 주세요.",
  prerequisite_missing: "먼저 완료해야 하는 과제가 있어요.",
  extraction_failed: "사진에서 정보를 읽지 못했어요. 다시 촬영해 주세요.",
  validation_failed: "입력값을 다시 확인해 주세요.",
  blocked_by_law: "법적으로 지금은 진행할 수 없는 단계예요.",
};

// Spring({code,message,details})과 AI({detail:{error,message,details}}) 양쪽을 받는다.
export function toAgentError(status, body, fallback) {
  const payload = body?.detail && typeof body.detail === "object" ? body.detail : body || {};
  const code = payload.error || payload.code;
  const message = payload.message || ERROR_MESSAGE[code] || fallback || `요청을 처리하지 못했어요. (${status})`;
  return new AgentError(message, { status, code, details: payload.details });
}

async function agentFetch(path, { method = "POST", body, label } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: authHeaders(body === undefined ? undefined : { "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new AgentError("네트워크에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.", { code: "network" });
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw toAgentError(response.status, payload, label && `${label}에 실패했어요.`);
  return payload;
}

// ui.payload 를 화면이 바로 쓸 수 있는 모양으로 고른다.
// 모르는 ui.type 은 reply 만 표시하도록 payload 를 비운다.
const KNOWN_UI = new Set(["profile_confirm", "question", "comparison", "doc_preview", "approval"]);

export function readUi(response) {
  const type = response?.ui?.type || "none";
  if (!KNOWN_UI.has(type)) return { type: "none", payload: {} };
  return { type, payload: response.ui.payload || {} };
}

// AI 는 options 를 [{value,label}] 로 준다. 문자열 배열도 받아 같은 모양으로 맞춘다.
export function questionOptions(payload) {
  return (payload?.options || []).map((option) =>
    typeof option === "string" ? { value: option, label: option } : option);
}

async function requireOk(res, label) {
  if (res.ok) return res;
  // S3 PUT 처럼 JSON 이 아닌 응답도 있다. 그 경우 상태 코드 메시지를 쓴다.
  const body = await res.json().catch(() => ({}));
  throw toAgentError(res.status, body, `${label}에 실패했어요.`);
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
export async function signUp({ email, password, passwordConfirm }) {
  if (MOCK) return delay({ memberId: "mock-member", accessToken: "mock-token", tokenType: "Bearer" });
  return authPost("/api/v1/auth/signup", { email, password, passwordConfirm });
}

export async function login({ email, password, passcode }) {
  const payload = MOCK
    ? await delay({ memberId: "mock-member", accessToken: "mock-token", tokenType: "Bearer" })
    : await authPost("/api/v1/auth/login", { email, password, passcode });
  saveToken(payload.accessToken);
  return payload;
}

async function authPost(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.message || "인증 요청을 처리하지 못했어요.");
  return payload;
}

export async function extractDocs({ arcFront, arcBack, passport }) {
  if (MOCK) return delay(MOCK_EXTRACT);
  return post("/api/ocr/extract", { arcFront, arcBack, passport });
}

export async function uploadAndExtract(file, documentType) {
  if (file.type !== "image/png") throw new Error("PNG 이미지만 업로드할 수 있어요.");
  if (MOCK) return delay(normalizeMockExtraction(MOCK_EXTRACT));

  const createUpload = await requireOk(await fetch("/api/v1/uploads", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ documentType }),
  }), "업로드 준비");
  const { uploadId, uploadUrl } = await createUpload.json();

  // presigned URL. Authorization 을 붙이면 S3 가 서명 불일치로 403 을 준다.
  await requireOk(await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": "image/png" },
    body: file,
  }), "사진 업로드");

  const extraction = await requireOk(await fetch("/api/v1/documents/extractions", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ uploadId }),
  }), "서류 인식");
  return normalizeExtraction(await extraction.json());
}

function normalizeExtraction(response) {
  const fields = response?.ui?.type === "profile_confirm" ? response.ui.payload?.fields || [] : [];
  return {
    profile: response?.state?.profile || {},
    fields,
    state: response?.state || {},
    confidence: Object.fromEntries(fields.map((field) => [field.key, field.confidence])),
    agentResponse: response,
  };
}

function normalizeMockExtraction(mock) {
  const readonly = new Set(["arc_no"]);
  const labels = {
    name_en: "이름", arc_no: "등록번호", nationality: "국적", visa_type: "체류자격",
    stay_expiry: "체류기간", addr_kr: "체류지", birth_date: "생년월일", sex: "성별",
  };
  const fields = Object.entries(mock.profile).map(([key, value]) => ({
    key, label: labels[key] || key, value, confidence: mock.confidence[key] ?? 1, editable: !readonly.has(key),
  }));
  return normalizeExtraction({
    reply: "신분증을 확인했습니다.",
    ui: { type: "profile_confirm", payload: { fields } },
    state: { session_id: "demo-001", profile: mock.profile },
  });
}

// 2) OCR 프로필 확정. message는 dirty 필드만 담은 JSON 문자열이다.
export async function confirmProfile(sessionId, dirtyFields) {
  if (MOCK) return delay({
    reply: "프로필을 확인했어요. 몇 가지만 더 여쭤볼게요.",
    ui: { type: "question", payload: { field: "phone_kr" } },
    state: { session_id: sessionId, profile: { ...MOCK_EXTRACT.profile, ...dirtyFields } },
  });

  return agentFetch("/api/profile/confirm", {
    body: { session_id: sessionId, message: JSON.stringify(dirtyFields) },
    label: "프로필 확인",
  });
}

// ── 화면 1. 세션 생성 ────────────────────────────────────────────────
// AI 는 { session_id } 가 아니라 AgentResponse 전체를 준다. session_id 는 state 에 있다.
export async function createSession(locale = "ko") {
  if (MOCK) return delay(mockAgentResponse({ session_id: "demo-001", locale }));
  return agentFetch(`/api/session?locale=${encodeURIComponent(locale)}`, { label: "세션 생성" });
}

// ── 화면 4. 상담 답변 제출 ───────────────────────────────────────────
export async function sendChat(sessionId, message) {
  if (MOCK) return delay(mockAgentResponse({ session_id: sessionId }, "알겠습니다."));
  return agentFetch("/api/chat", {
    body: { session_id: sessionId, message },
    label: "메시지 전송",
  });
}

// ── 화면 5. 과제 시작 ────────────────────────────────────────────────
// locked 과제면 409 prerequisite_missing 이 AgentError 로 올라온다.
export async function startAction(sessionId, actionId) {
  if (MOCK) return delay(mockAgentResponse({ session_id: sessionId }, "과제를 시작할게요."));
  return agentFetch(`/api/actions/${encodeURIComponent(actionId)}/start`, {
    body: { session_id: sessionId },
    label: "과제 시작",
  });
}

function mockAgentResponse(state, reply = "안녕하세요. 신분증부터 확인할게요.") {
  return {
    schema_version: SCHEMA_VERSION,
    reply,
    ui: { type: "none", payload: {} },
    state: { locale: "ko", profile: {}, tasks: [], documents: [], pending_approval: null, ...state },
  };
}

// 3) 룰 엔진 판정
export async function getVerdict(profileId, answers) {
  if (MOCK) return delay(mockVerdict(answers));
  return post("/api/verdict", { profileId, answers });
}

export async function previewAction(actionId, sessionId) {
  const response = await fetch(`/api/actions/${encodeURIComponent(actionId)}/preview`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ session_id: sessionId }),
  });
  await requireOk(response, "PDF 미리보기");
  return response.json();
}

export async function approveAction(actionId, sessionId, approved) {
  const response = await fetch(`/api/actions/${encodeURIComponent(actionId)}/approve`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ session_id: sessionId, approved }),
  });
  await requireOk(response, approved ? "실행 승인" : "실행 취소");
  return response.json();
}

export async function getLedger(sessionId) {
  const response = await fetch(`/api/ledger?session_id=${encodeURIComponent(sessionId)}`, {
    headers: authHeaders(),
  });
  await requireOk(response, "실행 이력 불러오기");
  return response.json();
}

export async function fetchDocument(url) {
  const response = await fetch(url, { headers: authHeaders() });
  await requireOk(response, "PDF 불러오기");
  return response.blob();
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

function delay(v, ms = 500) {
  return new Promise((r) => setTimeout(() => r(v), ms));
}
