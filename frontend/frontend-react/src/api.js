// 백엔드(Spring Boot) API 클라이언트.
// 목 모드가 필요한 경우에만 VITE_USE_MOCK=true로 실행한다.

const MOCK = import.meta.env.VITE_USE_MOCK === "true";
let mockDocuments = [];
let mockLedger = [];

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
const MEMBER_KEY = "settle_member_id";

export function readToken() {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

export function saveToken(token) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
}

export function readMemberId() {
  return window.localStorage.getItem(MEMBER_KEY) || "";
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(MEMBER_KEY);
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
  EMAIL_ALREADY_EXISTS: "이미 가입된 이메일이에요. 로그인하거나 다른 이메일을 사용해 주세요.",
  INVALID_CREDENTIALS: "이메일 또는 비밀번호를 확인해 주세요.",
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
    gender: "F",
  },
  // confidence < 0.95 → 사용자 확인 대상 (doc_builder.CONF_THRESHOLD)
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
  return authPost("/api/v1/auth/signup", { email: email.trim(), password, passwordConfirm });
}

export async function login({ email, password }) {
  const payload = MOCK
    ? await delay({ memberId: "mock-member", accessToken: "mock-token", tokenType: "Bearer" })
    : await authPost("/api/v1/auth/login", { email: email.trim(), password });
  saveToken(payload.accessToken);
  if (payload.memberId) window.localStorage.setItem(MEMBER_KEY, payload.memberId);
  return payload;
}

async function authPost(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AgentError("네트워크에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.", { code: "network" });
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw toAgentError(response.status, payload, "인증 요청을 처리하지 못했어요.");
  return payload;
}

export async function extractDocs({ arcFront, arcBack, passport }) {
  if (MOCK) return delay(MOCK_EXTRACT);
  return post("/api/ocr/extract", { arcFront, arcBack, passport });
}

export async function uploadAndExtract(file, documentType, locale = "ko") {
  if (file.type !== "image/png") throw new Error("PNG 이미지만 업로드할 수 있어요.");
  if (MOCK) return delay(normalizeMockExtraction(MOCK_EXTRACT, locale));

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

function normalizeMockExtraction(mock, locale = "ko") {
  const readonly = new Set(["arc_no"]);
  const labels = {
    name_en: "이름", arc_no: "등록번호", nationality: "국적", visa_type: "체류자격",
    stay_expiry: "체류기간", addr_kr: "체류지", birth_date: "생년월일", gender: "성별",
  };
  const fields = Object.entries(mock.profile).map(([key, value]) => ({
    key, label: labels[key] || key, value, confidence: mock.confidence[key] ?? 1, editable: !readonly.has(key),
  }));
  return normalizeExtraction({
    reply: locale === "en" ? "I checked your documents." : "신분증을 확인했습니다.",
    ui: { type: "profile_confirm", payload: { fields } },
    state: { session_id: "demo-001", locale, profile: mock.profile },
  });
}

// 2) OCR 프로필 확정. message는 dirty 필드만 담은 JSON 문자열이다.
export async function confirmProfile(sessionId, dirtyFields, locale = "ko") {
  if (MOCK) return delay({
    reply: locale === "en"
      ? "Profile confirmed. Ask me anything about settling in Korea — bank accounts, visas, telecom, anything."
      : "프로필을 확인했어요. 한국 정착에 필요한 것은 무엇이든 물어보세요. 체류·계좌·통신 뭐든 도와드릴게요.",
    ui: { type: "none", payload: {} },
    state: { session_id: sessionId, locale, profile: { ...MOCK_EXTRACT.profile, ...dirtyFields } },
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
export async function sendChat(sessionId, message, locale = "ko") {
  if (MOCK) return delay(mockAgentResponse({ session_id: sessionId, locale }, locale === "en" ? "Got it." : "알겠습니다."));
  return agentFetch("/api/chat", {
    body: { session_id: sessionId, message },
    label: "메시지 전송",
  });
}

// ── 화면 5. 과제 시작 ────────────────────────────────────────────────
// locked 과제면 409 prerequisite_missing 이 AgentError 로 올라온다.
export async function startAction(sessionId, actionId, locale = "ko") {
  if (MOCK) return delay(mockAgentResponse({ session_id: sessionId, locale }, locale === "en" ? "Let's start this task." : "과제를 시작할게요."));
  return agentFetch(`/api/actions/${encodeURIComponent(actionId)}/start`, {
    body: { session_id: sessionId },
    label: "과제 시작",
  });
}

function mockAgentResponse(state, reply) {
  const locale = state.locale || "ko";
  return {
    schema_version: SCHEMA_VERSION,
    reply: reply || (locale === "en" ? "If you upload your ID, I'll tell you what you need to do." : "안녕하세요. 신분증부터 확인할게요."),
    ui: { type: "none", payload: {} },
    state: { locale: "ko", profile: {}, tasks: [], documents: [], pending_approval: null, ...state },
  };
}

// 3) 룰 엔진 판정
export async function getVerdict(profileId, answers, locale = "ko") {
  if (MOCK) return delay(mockVerdict(answers, locale));
  return post("/api/verdict", { profileId, answers });
}

export async function previewAction(actionId, sessionId, locale = "ko") {
  if (MOCK) {
    const pdfUrl = `/mock/documents/${sessionId}-${actionId}.pdf`;
    const integrated = actionId !== "open_bank_account";
    const actionNames = {
      alien_registration: ["외국인등록", "Alien registration"],
      residence_change: ["체류지 변경", "Change of residence"],
      work_activity: ["체류자격외활동허가", "Activity permit"],
      open_bank_account: ["은행 계좌 개설", "Open a bank account"],
    };
    const actionName = actionNames[actionId] || [actionId, actionId];
    const mockDocument = {
      id: `${sessionId}-${actionId}`,
      title: integrated
        ? (locale === "en" ? "Integrated Application (Report)" : "통합신청서(신고서)")
        : (locale === "en" ? "Bank account application" : "계좌개설신청서"),
      created_at: new Date().toISOString(),
      preview_url: pdfUrl,
      pdf_url: pdfUrl,
    };
    mockDocuments = [mockDocument, ...mockDocuments.filter((document) => document.id !== mockDocument.id)];
    const pendingApproval = {
      action_id: actionId,
      title: actionName[locale === "en" ? 1 : 0],
      summary: [locale === "en" ? "Submit the completed application" : "작성된 신청서 제출"],
      evidence: [],
      risk_level: "L2",
    };
    return delay({
      schema_version: SCHEMA_VERSION,
      reply: locale === "en" ? "Your document is ready." : "서류를 작성했습니다.",
      ui: { type: "doc_preview", payload: { document_id: mockDocument.id, ...mockDocument, warnings: [] } },
      state: { session_id: sessionId, locale, profile: {}, tasks: [], documents: mockDocuments, pending_approval: pendingApproval },
    });
  }
  const response = await fetch(`/api/actions/${encodeURIComponent(actionId)}/preview`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ session_id: sessionId }),
  });
  await requireOk(response, "PDF 미리보기");
  return response.json();
}

export async function approveAction(actionId, sessionId, approved, locale = "ko") {
  if (MOCK) {
    if (approved && !mockLedger.some((entry) => entry.action === actionId)) {
      mockLedger = [{ action: actionId, risk_level: "L2", approved_at: new Date().toISOString(), evidence: [] }];
    }
    return delay({
      schema_version: SCHEMA_VERSION,
      reply: approved
        ? (locale === "en" ? "The approved action has been completed." : "승인한 작업을 실행했습니다.")
        : (locale === "en" ? "The action was canceled." : "실행을 취소했습니다."),
      ui: { type: "none", payload: {} },
      state: { session_id: sessionId, locale, profile: {}, tasks: [], documents: mockDocuments, pending_approval: null },
    });
  }
  const response = await fetch(`/api/actions/${encodeURIComponent(actionId)}/approve`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ session_id: sessionId, approved }),
  });
  await requireOk(response, approved ? "실행 승인" : "실행 취소");
  return response.json();
}

export async function getLedger(sessionId) {
  if (MOCK) return delay(mockLedger);
  const response = await fetch(`/api/ledger?session_id=${encodeURIComponent(sessionId)}`, {
    headers: authHeaders(),
  });
  await requireOk(response, "실행 이력 불러오기");
  return response.json();
}

export async function fetchDocument(url) {
  if (MOCK) {
    const title = url.includes("open_bank_account")
      ? "Bank Account Application"
      : "Integrated Application (Report)";
    return delay(new Blob([createMockPdf(title)], { type: "application/pdf" }));
  }
  const response = await fetch(url, { headers: authHeaders() });
  await requireOk(response, "PDF 불러오기");
  return response.blob();
}

export function nationalityLabel(code) {
  return NATIONALITY_LABEL[code] || code;
}

// ── 판정 룰(프론트 목). 실제 판정은 백엔드 rules 엔진이 담당 ──────────
function mockVerdict(answers = {}, locale = "ko") {
  const passportIssue = answers.scenario === "passport" || answers.passportIssue === true;
  const noPhone = answers.phone === "no";
  const noCert = answers.cert === "no";
  const kind = passportIssue ? "passport" : noPhone ? "phone" : noCert ? "cert" : "ready";
  if (locale === "en") return mockVerdictEnglish(kind);
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

function mockVerdictEnglish(kind) {
  const sources = [
    "Financial identity verification guide — Foreign nationals §3.2",
    "Restricted-account limit release requirements (revised Jan 2026)",
    "KB Kookmin Bank student account-opening criteria",
  ];
  if (kind === "passport") return {
    kind, sources,
    headline: "One document needs attention",
    summary: "Your passport expires in four months. Renew it before visiting because the bank requires at least six months of validity.",
    blocker: { title: "Passport validity", badge: "Extracted", body: "Read from passport: expires 2026-12-09 — below the six-month requirement. Your residence card is fine." },
    limited: { status: "After renewal", ready: false, body: "Everything else passed. Renew your passport to continue." },
    regular: { status: "Not yet", body: "A standard account requires at least six months of stay history or proof of income." },
  };
  if (kind === "phone") return {
    kind, sources,
    headline: "One more thing before you are ready",
    summary: "You need a Korean phone number registered in your name before visiting the bank.",
    blocker: { title: "Phone in your name", badge: "Required", body: "The branch verifies you by text message. A prepaid number is acceptable, but a friend's number is not." },
    limited: { status: "After activation", ready: false, body: "Your residence card, passport, and enrollment certificate are ready." },
    regular: { status: "Not yet", body: "A standard account requires at least six months of stay history or proof of income." },
  };
  if (kind === "cert") return {
    kind, sources,
    headline: "Almost ready — one document remains",
    summary: "Bring an enrollment certificate or admission letter. You do not need to scan it; bring the paper original.",
    blocker: { title: "Enrollment certificate", badge: "Paper only", body: "Print it from your school portal and submit it at the branch." },
    limited: { status: "After issuance", ready: false, body: "Your residence card, passport, and phone are ready." },
    regular: { status: "Not yet", body: "A standard account requires at least six months of stay history or proof of income." },
  };
  return {
    kind, sources,
    headline: "You can visit the bank today",
    summary: "You have what you need for a restricted account. You may be able to raise the limit after six months.",
    blocker: null,
    limited: { status: "Ready", ready: true, body: "Bring your residence card, passport, enrollment certificate, and phone registered in your name." },
    regular: { status: "Not yet", body: "A standard account requires at least six months of stay history or proof of income." },
  };
}

function delay(v, ms = 500) {
  return new Promise((r) => setTimeout(() => r(v), ms));
}

function createMockPdf(title) {
  const escapedTitle = title.replace(/[()\\]/g, "\\$&");
  const content = `BT /F1 18 Tf 72 720 Td (${escapedTitle}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(new TextEncoder().encode(pdf).length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = new TextEncoder().encode(pdf).length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  pdf += offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("");
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return pdf;
}
