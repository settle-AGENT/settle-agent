import React, { useEffect, useRef, useState } from "react";
import { BridgeMark, TopBar, Rail, PrimaryButton, Field, QuestionCard, TaskCard } from "./components.jsx";
import {
  signUp, login, uploadAndExtract, confirmProfile, getVerdict, previewAction, approveAction, getLedger,
  fetchDocument, nationalityLabel,
  createSession, sendChat, startAction, readUi, questionOptions, clearToken, readMemberId,
} from "./api.js";
import { captureVideoFrameAsPng, convertImageToPng } from "./image.js";

const PURPOSES = ["등록금 납부", "아르바이트 급여", "본국 송금", "생활비", "장학금"];
const SCAN_PAGES = [
  { key: "arcFront", docType: "arc_front", label: "외국인등록증 앞면", sub: "앞면" },
  { key: "arcBack", docType: "arc_back", label: "외국인등록증 뒷면", sub: "뒷면" },
  { key: "passport", docType: "passport", label: "여권", sub: "여권 사진면" },
];
const PREVIEW_ACTION_ID = "open_bank_account";
const ONBOARDING_PROGRESS_KEY = "settle_onboarding_progress_v1";
const PROFILE_DRAFT_KEY = "settle_profile_draft_v1";
const EMPTY_AUTH = { email: "", password: "", passwordConfirm: "", passcode: "" };
const EMPTY_ANSWERS = { phone: null, cert: null, purposes: {} };
const PROFILE_LABELS = {
  name_en: "이름", arc_no: "등록번호", nationality: "국적", visa_type: "체류자격",
  stay_expiry: "체류기간", addr_kr: "체류지", birth_date: "생년월일", sex: "성별",
};
const REUSABLE_PROFILE_KEYS = ["name_en", "arc_no", "nationality", "visa_type", "stay_expiry"];
const EMAIL_PATTERN = /^(?=.{1,64}@)[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z]{2,63})+$/;

function readOnboardingProgress() {
  try {
    const progress = JSON.parse(window.localStorage.getItem(ONBOARDING_PROGRESS_KEY) || "null");
    if (!progress || typeof progress !== "object") return null;
    return {
      lang: progress.lang === "ko" ? "ko" : "en",
      lastStep: Number.isInteger(progress.lastStep) ? progress.lastStep : 1,
      completedScans: Array.isArray(progress.completedScans)
        ? progress.completedScans.filter((key) => SCAN_PAGES.some((page) => page.key === key))
        : [],
      answers: progress.answers && typeof progress.answers === "object"
        ? { ...EMPTY_ANSWERS, ...progress.answers, purposes: progress.answers.purposes || {} }
        : { ...EMPTY_ANSWERS },
      updatedAt: progress.updatedAt || null,
      memberId: typeof progress.memberId === "string" ? progress.memberId : "",
    };
  } catch {
    return null;
  }
}

function readProfileDraft(expectedMemberId = "") {
  try {
    const draft = JSON.parse(window.sessionStorage.getItem(PROFILE_DRAFT_KEY) || "null");
    if (!draft || typeof draft !== "object") return null;
    if (expectedMemberId && draft.memberId && draft.memberId !== expectedMemberId) return null;
    return {
      profileDraft: draft.profileDraft && typeof draft.profileDraft === "object" ? draft.profileDraft : {},
      dirtyFields: draft.dirtyFields && typeof draft.dirtyFields === "object" ? draft.dirtyFields : {},
    };
  } catch {
    return null;
  }
}

function extractionFromSession(response) {
  const profile = response?.state?.profile || {};
  const responseFields = response?.ui?.type === "profile_confirm"
    ? response.ui.payload?.fields || []
    : [];
  const fields = responseFields.length
    ? responseFields
    : Object.entries(profile)
        .filter(([, value]) => ["string", "number"].includes(typeof value))
        .map(([key, value]) => ({
          key,
          label: PROFILE_LABELS[key] || key,
          value,
          editable: key !== "arc_no",
        }));
  return {
    profile,
    fields,
    state: response?.state || {},
    agentResponse: response,
  };
}

function passwordChecks(password) {
  return [
    { label: "8~64자", met: password.length >= 8 && password.length <= 64 },
    { label: "영문 포함", met: /[A-Za-z]/.test(password) },
    { label: "숫자 포함", met: /\d/.test(password) },
    { label: "특수문자 포함", met: /[^A-Za-z0-9]/.test(password) },
    { label: "영문·숫자·특수문자만", met: /^[\x21-\x7E]+$/.test(password) },
  ];
}

function authErrorMessage(error) {
  if (error?.code === "EMAIL_ALREADY_EXISTS") {
    return "이미 가입된 이메일이에요. 로그인하거나 다른 이메일을 사용해 주세요.";
  }
  const validationReasons = Array.isArray(error?.details)
    ? [...new Set(error.details.map((detail) => detail?.reason).filter(Boolean))]
    : [];
  if (error?.code === "validation_failed" && validationReasons.length) {
    return validationReasons.join(" ");
  }
  return error instanceof Error ? error.message : "인증 요청을 처리하지 못했어요.";
}

const card = {
  padding: 15, borderRadius: 14, border: "1px solid var(--line)", background: "#fff",
};
const H2 = { margin: 0, fontSize: 25, lineHeight: 1.25, fontWeight: 800, letterSpacing: "-0.035em" };
const SUB = { margin: "7px 0 0", fontSize: 14, lineHeight: 1.5, color: "var(--muted)" };
const mono = { fontFamily: "'IBM Plex Mono',monospace" };

export default function App() {
  const [step, setStep] = useState(0);
  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(window.localStorage.getItem("settle_access_token")));
  const [memberId, setMemberId] = useState(readMemberId);
  const [authMode, setAuthMode] = useState("login");
  const [auth, setAuth] = useState(() => ({ ...EMPTY_AUTH }));
  const [authMessage, setAuthMessage] = useState("");
  const [authMessageType, setAuthMessageType] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [savedProgress, setSavedProgress] = useState(() => {
    const progress = readOnboardingProgress();
    return progress?.memberId && memberId && progress.memberId !== memberId ? null : progress;
  });
  const [lang, setLang] = useState(() => savedProgress?.lang || "en");
  const [nat, setNat] = useState(null);
  const [exitConfirmOpen, setExitConfirmOpen] = useState(false);

  // ── 에이전트 단일 스토어 ──
  // 서버 state 가 진실의 원천이다. 부분 병합하지 않고 통째로 교체한다.
  const [agentState, setAgentState] = useState(null);
  const [ui, setUi] = useState({ type: "none", payload: {} });
  const [messages, setMessages] = useState([]);
  const [toast, setToast] = useState("");
  const [sessionLoading, setSessionLoading] = useState(false);

  const [scan, setScan] = useState(0);
  const [shots, setShots] = useState({});
  const [completedScans, setCompletedScans] = useState(() => savedProgress?.completedScans || []);
  const [captureError, setCaptureError] = useState("");
  const [captureLoading, setCaptureLoading] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraStarting, setCameraStarting] = useState(false);
  const [extract, setExtract] = useState(null);
  const [profileDraft, setProfileDraft] = useState(() => readProfileDraft(memberId)?.profileDraft || {});
  const [dirtyFields, setDirtyFields] = useState(() => readProfileDraft(memberId)?.dirtyFields || {});
  const [profileErrors, setProfileErrors] = useState({});
  const [profileSubmitting, setProfileSubmitting] = useState(false);

  const [answers, setAnswers] = useState(() => savedProgress?.answers || { ...EMPTY_ANSWERS });
  const [verdict, setVerdict] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState("");
  const [approval, setApproval] = useState(null);
  const [approvalLoading, setApprovalLoading] = useState(false);
  const [approvalError, setApprovalError] = useState("");
  const [ledger, setLedger] = useState([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [ledgerError, setLedgerError] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [taskBusy, setTaskBusy] = useState("");
  const [docs, setDocs] = useState(null);
  const [openDoc, setOpenDoc] = useState(null);
  const chatEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const nativeCameraInputRef = useRef(null);
  const videoRef = useRef(null);
  const cameraStreamRef = useRef(null);
  const cameraRequestRef = useRef(false);
  const pastedImageHandlerRef = useRef(null);
  const navigationHistoryRef = useRef([]);
  const progressRef = useRef(savedProgress);

  const stopCamera = () => {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;
    setCameraOpen(false);
  };

  const startCamera = async (allowNativeFallback = true) => {
    if (cameraRequestRef.current || cameraStreamRef.current) return;
    cameraRequestRef.current = true;
    setCaptureError("");
    setCameraStarting(true);
    let timeoutId;
    let timedOut = false;
    let streamRequest;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        if (allowNativeFallback) nativeCameraInputRef.current?.click();
        else setCaptureError("이 브라우저는 웹 카메라를 지원하지 않아요. 기기 카메라로 열기를 눌러 주세요.");
        return;
      }
      streamRequest = navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      const timeout = new Promise((_, reject) => {
        timeoutId = window.setTimeout(() => {
          timedOut = true;
          reject(new Error("브라우저가 카메라 요청에 응답하지 않았어요. Chrome를 완전히 종료한 뒤 다시 실행해 주세요."));
        }, 8000);
      });
      cameraStreamRef.current = await Promise.race([streamRequest, timeout]);
      setCameraOpen(true);
    } catch (error) {
      if (timedOut) streamRequest?.then((stream) => stream.getTracks().forEach((track) => track.stop())).catch(() => {});
      setCaptureError(error?.name === "NotAllowedError" ? "카메라 권한을 허용해 주세요." : error instanceof Error ? error.message : "카메라를 열지 못했어요.");
    } finally {
      window.clearTimeout(timeoutId);
      cameraRequestRef.current = false;
      setCameraStarting(false);
    }
  };

  useEffect(() => {
    if (step !== 4) return;
    const frame = requestAnimationFrame(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }));
    return () => cancelAnimationFrame(frame);
  }, [step, answers.phone, answers.cert, answers.purposes, verdict, chatLoading]);

  useEffect(() => {
    if (cameraOpen && videoRef.current && cameraStreamRef.current) {
      videoRef.current.srcObject = cameraStreamRef.current;
      videoRef.current.play().catch(() => setCaptureError("카메라 미리보기를 시작하지 못했어요."));
    }
  }, [cameraOpen]);

  useEffect(() => () => cameraStreamRef.current?.getTracks().forEach((track) => track.stop()), []);

  useEffect(() => () => {
    if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
  }, [previewBlobUrl]);

  // 세션은 POST /api/session 이 발급한 값 하나뿐이다.
  // 임의의 폴백을 쓰면 Spring 의 소유권 검증에서 403 이 난다.
  const sessionId = agentState?.session_id || null;
  const documents = agentState?.documents || [];

  useEffect(() => {
    if (step !== 9 || !sessionId) return;
    let active = true;
    setLedgerLoading(true);
    setLedgerError("");
    getLedger(sessionId)
      .then((entries) => { if (active) setLedger(Array.isArray(entries) ? entries : []); })
      .catch((error) => { if (active) setLedgerError(error instanceof Error ? error.message : "실행 이력을 불러오지 못했어요."); })
      .finally(() => { if (active) setLedgerLoading(false); });
    return () => { active = false; };
  }, [step, sessionId]);

  useEffect(() => {
    if (step !== 2) return;
    return () => {
      cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
      setCameraOpen(false);
      setCameraStarting(false);
    };
  }, [step]);

  useEffect(() => {
    if (step !== 2) return;
    const pasteImage = (event) => {
      const imageItem = [...(event.clipboardData?.items || [])].find((item) => item.type.startsWith("image/"));
      const image = imageItem?.getAsFile();
      if (!image) {
        setCaptureError("클립보드에 이미지가 없어요. 이미지를 복사한 뒤 다시 붙여넣어 주세요.");
        return;
      }
      event.preventDefault();
      pastedImageHandlerRef.current?.(image);
    };
    window.addEventListener("paste", pasteImage);
    return () => window.removeEventListener("paste", pasteImage);
  }, [step]);

  useEffect(() => {
    if (!isAuthenticated || !memberId || step < 1 || step > 9) return;
    const previous = progressRef.current || {};
    const next = {
      ...previous,
      lang,
      lastStep: Math.max(previous.lastStep || 1, step),
      completedScans,
      answers,
      memberId,
      updatedAt: new Date().toISOString(),
    };
    progressRef.current = next;
    window.localStorage.setItem(ONBOARDING_PROGRESS_KEY, JSON.stringify(next));
    setSavedProgress(next);
  }, [answers, completedScans, isAuthenticated, lang, memberId, step]);

  useEffect(() => {
    if (!memberId || step !== 3) return;
    window.sessionStorage.setItem(PROFILE_DRAFT_KEY, JSON.stringify({
      memberId,
      profileDraft,
      dirtyFields,
    }));
  }, [dirtyFields, memberId, profileDraft, step]);

  useEffect(() => {
    if (!isAuthenticated || step < 1 || step > 5) return undefined;
    const confirmRefresh = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", confirmRefresh);
    return () => window.removeEventListener("beforeunload", confirmRefresh);
  }, [isAuthenticated, step]);

  const go = (nextStep, { replace = false } = {}) => {
    if (nextStep === step) return;
    if (!replace) navigationHistoryRef.current.push(step);
    setStep(nextStep);
  };

  const back = (fallback = 0) => {
    const previousStep = navigationHistoryRef.current.pop();
    setStep(previousStep ?? fallback);
  };

  const requestOnboardingExit = () => setExitConfirmOpen(true);

  const exitOnboarding = () => {
    stopCamera();
    setExitConfirmOpen(false);
    navigationHistoryRef.current = [];
    setStep(0);
  };

  const openPdfPreview = async () => {
    if (previewLoading) return;
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const response = applyAgent(await previewAction(PREVIEW_ACTION_ID, sessionId));
      const responseUi = readUi(response);
      if (responseUi.type === "question") {
        go(4);
        return;
      }
      if (responseUi.type === "approval") {
        return;
      }
      if (responseUi.type !== "doc_preview") {
        throw new Error(response?.reply || "PDF 미리보기 응답을 확인해 주세요.");
      }
      const payload = responseUi.payload;
      const blob = await fetchDocument(payload.preview_url);
      const nextBlobUrl = URL.createObjectURL(blob);
      setPreviewBlobUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return nextBlobUrl;
      });
      setPreview(payload);
      go(10);
    } catch (error) {
      if (!handleAuthError(error)) setPreviewError(error instanceof Error ? error.message : "PDF를 불러오지 못했어요.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const openStoredDocument = async (document) => {
    setPreviewError("");
    try {
      const blob = await fetchDocument(document.preview_url);
      const nextBlobUrl = URL.createObjectURL(blob);
      setPreviewBlobUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return nextBlobUrl;
      });
      setPreview({ ...document, warnings: [] });
      go(10);
    } catch (error) {
      if (!handleAuthError(error)) setPreviewError(error instanceof Error ? error.message : "PDF를 불러오지 못했어요.");
    }
  };

  const downloadPdf = async (document) => {
    try {
      const blob = await fetchDocument(document.pdf_url);
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = `${document.title || "document"}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      if (!handleAuthError(error)) setPreviewError(error instanceof Error ? error.message : "PDF를 다운로드하지 못했어요.");
    }
  };

  const decideApproval = async (approved) => {
    if (approvalLoading || !approval?.action_id) return;
    setApprovalLoading(true);
    setApprovalError("");
    try {
      applyAgent(await approveAction(approval.action_id, sessionId, approved));
    } catch (error) {
      if (!handleAuthError(error)) setApprovalError(error instanceof Error ? error.message : "승인 요청을 처리하지 못했어요.");
    } finally {
      setApprovalLoading(false);
    }
  };

  // AgentResponse 처리 순서는 계약대로 setState → render(ui) → appendMessage(reply).
  const applyAgent = (response) => {
    if (response?.state) setAgentState(response.state);
    setUi(readUi(response));
    if (response?.reply) setMessages((current) => [...current, { from: "agent", text: response.reply }]);
    const nextApproval = response?.ui?.type === "approval"
      ? response.ui.payload
      : response?.state?.pending_approval;
    setApproval(nextApproval || null);
    return response;
  };

  // 401/403 이면 세션을 이어갈 방법이 없다. 토큰을 버리고 로그인부터 다시 받는다.
  // 처리했으면 true — 호출부는 자기 화면 오류를 띄우지 않고 빠진다.
  const handleAuthError = (error) => {
    if (error?.status !== 401 && error?.status !== 403) return false;
    clearToken();
    setIsAuthenticated(false);
    setMemberId("");
    setAgentState(null);
    setUi({ type: "none", payload: {} });
    setMessages([]);
    setApproval(null);
    setAuthMode("login");
    setAuthMessage(error.message || "로그인이 만료됐어요. 다시 로그인해 주세요.");
    setAuthMessageType("error");
    navigationHistoryRef.current = [];
    go(-1, { replace: true });
    return true;
  };

  const resumeSession = async () => {
    if (sessionLoading) return;
    setSessionLoading(true);
    setToast("");
    try {
      const response = applyAgent(await createSession(lang));
      const restored = extractionFromSession(response);
      const restoredProfile = restored.profile || {};
      const restoredFields = restored.fields || [];
      if (restoredFields.length > 0) {
        const privateDraft = readProfileDraft(memberId);
        const serverDraft = Object.fromEntries(
          restoredFields.map((field) => [field.key, field.value ?? restoredProfile[field.key] ?? ""])
        );
        setExtract(restored);
        setProfileDraft({ ...serverDraft, ...(privateDraft?.profileDraft || {}) });
        setDirtyFields(privateDraft?.dirtyFields || {});
        setProfileErrors({});
        setNat(restoredProfile.nationality || null);
      }

      const lastStep = progressRef.current?.lastStep || 1;
      const responseUi = readUi(response);
      const hasReusableProfile = REUSABLE_PROFILE_KEYS.every((key) => restoredProfile[key]);
      const allScansCompleted = SCAN_PAGES.every((page) => completedScans.includes(page.key));
      if (hasReusableProfile && completedScans.length === 0) {
        setCompletedScans(SCAN_PAGES.map((page) => page.key));
      }
      const tasks = response?.state?.tasks || [];
      const storedDocuments = response?.state?.documents || [];
      let targetStep = 2;
      if (lastStep >= 7 && storedDocuments.length > 0) targetStep = 7;
      else if (lastStep >= 5 && tasks.length > 0) targetStep = 5;
      else if (responseUi.type === "question" || (lastStep >= 4 && hasReusableProfile)) targetStep = 4;
      else if (restoredFields.length > 0 && (lastStep >= 3 || allScansCompleted || hasReusableProfile)) targetStep = 3;
      go(targetStep);
    } catch (error) {
      if (!handleAuthError(error)) setToast(error?.message || "이전 진행 내용을 불러오지 못했어요.");
    } finally {
      setSessionLoading(false);
    }
  };

  const approvalModal = approval
    ? <ApprovalModal approval={approval} loading={approvalLoading} error={approvalError} onDecision={decideApproval} />
    : null;
  const activeModal = exitConfirmOpen
    ? <ExitConfirmModal onContinue={() => setExitConfirmOpen(false)} onExit={exitOnboarding} />
    : approvalModal;

  const openCabinetFromHome = async () => {
    if (sessionLoading) return;
    setSessionLoading(true);
    setToast("");
    try {
      const response = agentState?.session_id ? null : await createSession(lang);
      if (response) applyAgent(response);
      if (!(response?.state?.session_id || agentState?.session_id)) {
        throw new Error("상담 세션을 확인하지 못했어요.");
      }
      go(9);
    } catch (error) {
      if (!handleAuthError(error)) setToast(error?.message || "서류함을 불러오지 못했어요.");
    } finally {
      setSessionLoading(false);
    }
  };

  // ── 0 스플래시 ──
  if (step === 0)
    return (
      <Shell modal={activeModal}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 26, padding: "40px 34px" }}>
          <BridgeMark size={104} />
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <div style={{ fontFamily: "'Noto Sans KR',sans-serif", fontSize: 34, fontWeight: 700, letterSpacing: "-0.03em" }}>첫계좌</div>
            <div style={{ ...mono, fontSize: 12.5, letterSpacing: "0.28em", textTransform: "uppercase", color: "var(--muted)" }}>Firstaccount</div>
          </div>
          <div style={{ width: 34, height: 1, background: "var(--line)" }} />
          <div style={{ fontSize: 15, lineHeight: 1.55, color: "oklch(0.45 0.012 60)", textAlign: "center", maxWidth: 250 }}>
            은행은 한 번만 가세요.<br />서류는 저희가 먼저 준비해요.
          </div>
        </div>
        <div style={{ padding: "0 30px 40px", display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <div style={{ padding: "7px 13px", borderRadius: 999, background: "oklch(0.93 0.008 60)", ...mono, fontSize: 11, fontWeight: 700, letterSpacing: "0.1em" }}>
            D-2 STUDENT VISA · BETA
          </div>
          {isAuthenticated && savedProgress && (
            <div className="saved-progress-note" role="status">
              <span aria-hidden="true">✓</span>
              <div><b>진행 내용이 임시 저장되어 있어요</b><small>마지막 진행 단계와 선택 내용을 안전하게 불러옵니다.</small></div>
            </div>
          )}
          <div style={{ width: "100%" }}>
            <PrimaryButton disabled={sessionLoading} onClick={() => {
              if (isAuthenticated && savedProgress) resumeSession();
              else if (isAuthenticated) go(1);
              else {
                setAuthMode("login");
                go(-1);
              }
            }}>{sessionLoading ? "이전 진행 불러오는 중…" : isAuthenticated && savedProgress ? "이어서 하기" : "시작하기"}</PrimaryButton>
          </div>
          {isAuthenticated && savedProgress && (
            <button type="button" onClick={() => go(1)} className="text-action">언어 설정부터 다시 보기</button>
          )}
          {isAuthenticated && (
            <div onClick={openCabinetFromHome} className="tap" style={{ width: "100%", minHeight: 50, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 14, border: "1px solid oklch(0.85 0.01 60)", background: "#fff", fontSize: 14, fontWeight: 700 }}>
              <span aria-hidden="true">🗂️</span> {sessionLoading ? "서류함 불러오는 중…" : "내 서류함 열기"}
            </div>
          )}
          {toast && <div role="alert" className="capture-error" style={{ margin: 0 }}>{toast}</div>}
        </div>
      </Shell>
    );

  // ── 인증 ──
  if (step === -1) {
    const signup = authMode === "signup";
    const normalizedEmail = auth.email.trim();
    const validEmail = normalizedEmail.length <= 254 && EMAIL_PATTERN.test(normalizedEmail);
    const rules = passwordChecks(auth.password);
    const validPassword = rules.every((rule) => rule.met);
    const passwordMatches = Boolean(auth.passwordConfirm) && auth.password === auth.passwordConfirm;
    const canSubmit = signup
      ? validEmail && validPassword && passwordMatches
      : validEmail && auth.password.length >= 8 && /^\d{4}$/.test(auth.passcode);
    const clearAuthError = () => {
      if (authMessageType !== "error") return;
      setAuthMessage("");
      setAuthMessageType("");
    };
    const updateAuth = (key) => (e) => {
      setAuth((value) => ({ ...value, [key]: e.target.value }));
      clearAuthError();
    };
    const switchAuthMode = () => {
      setAuthMode(signup ? "login" : "signup");
      setAuth({ ...EMPTY_AUTH });
      setAuthMessage("");
      setAuthMessageType("");
    };
    const submitAuth = async (e) => {
      e.preventDefault();
      if (!canSubmit || authLoading) return;
      setAuthLoading(true);
      setAuthMessage("");
      setAuthMessageType("");
      try {
        if (signup) {
          await signUp(auth);
          setAuthMode("login");
          setAuth({ ...EMPTY_AUTH });
          setAuthMessage("회원가입이 완료됐어요. 새 계정으로 로그인해 주세요.");
          setAuthMessageType("success");
          return;
        }
        const response = await login(auth);
        const nextMemberId = String(response?.memberId || readMemberId());
        if (progressRef.current?.memberId && progressRef.current.memberId !== nextMemberId) {
          progressRef.current = null;
          window.localStorage.removeItem(ONBOARDING_PROGRESS_KEY);
          setSavedProgress(null);
          setCompletedScans([]);
          setAnswers({ ...EMPTY_ANSWERS });
          window.sessionStorage.removeItem(PROFILE_DRAFT_KEY);
        }
        setMemberId(nextMemberId);
        setIsAuthenticated(true);
        go(1);
      } catch (error) {
        setAuthMessage(authErrorMessage(error));
        setAuthMessageType("error");
      } finally {
        setAuthLoading(false);
      }
    };
    return (
      <Shell modal={activeModal}>
        <TopBar title={signup ? "회원가입" : "로그인"} onBack={() => back(0)} />
        <div style={{ padding: "18px 26px 12px" }}>
          <BridgeMark size={56} />
          <h2 style={{ ...H2, marginTop: 20 }}>{signup ? "첫계좌를 시작해요" : "다시 만나서 반가워요"}</h2>
          <p style={SUB}>{signup ? "사용할 이메일과 안전한 비밀번호를 입력해 주세요." : "이메일과 비밀번호, 4자리 Passcode를 입력해 주세요."}</p>
        </div>
        <form onSubmit={submitAuth} className="scroll" style={{ padding: "12px 26px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
          {authMessage && <div role={authMessageType === "error" ? "alert" : "status"} className={`auth-notice ${authMessageType}`}>{authMessage}</div>}
          <AuthInput label="이메일" type="email" value={auth.email} onChange={updateAuth("email")} placeholder="name@example.com" autoComplete="email" autoCapitalize="none" spellCheck={false} maxLength={254} aria-invalid={Boolean(auth.email) && !validEmail} />
          {auth.email && !validEmail && <FieldHint tone="error">영문 이메일 형식으로 입력해 주세요. (예: name@example.com)</FieldHint>}
          <AuthInput label="비밀번호" type="password" value={auth.password} onChange={updateAuth("password")} placeholder="비밀번호를 입력하세요" autoComplete={signup ? "new-password" : "current-password"} maxLength={64} aria-invalid={signup && Boolean(auth.password) && !validPassword} />
          {signup ? (
            <>
              <div className="password-guide" aria-label="비밀번호 조건" aria-live="polite">
                <strong>비밀번호 조건</strong>
                <div>{rules.map((rule) => <span key={rule.label} className={auth.password && rule.met ? "met" : ""}>{auth.password && rule.met ? "✓" : "•"} {rule.label}</span>)}</div>
              </div>
              <AuthInput label="비밀번호 확인" type="password" value={auth.passwordConfirm} onChange={updateAuth("passwordConfirm")} placeholder="비밀번호를 다시 입력하세요" autoComplete="new-password" maxLength={64} aria-invalid={Boolean(auth.passwordConfirm) && !passwordMatches} />
              {auth.passwordConfirm && !passwordMatches && <FieldHint tone="error">입력한 비밀번호가 서로 일치하지 않아요.</FieldHint>}
              {passwordMatches && <FieldHint tone="success">비밀번호가 일치해요.</FieldHint>}
            </>
          ) : (
            <AuthInput label="Passcode" type="password" value={auth.passcode} onChange={(e) => { setAuth((value) => ({ ...value, passcode: e.target.value.replace(/\D/g, "").slice(0, 4) })); clearAuthError(); }} placeholder="4자리 숫자" inputMode="numeric" maxLength={4} autoComplete="one-time-code" />
          )}
        </form>
        <div style={{ padding: "12px 26px 34px" }}>
          <PrimaryButton disabled={!canSubmit || authLoading} onClick={() => submitAuth({ preventDefault() {} })}>{authLoading ? "처리 중…" : signup ? "회원가입" : "로그인"}</PrimaryButton>
          <button type="button" onClick={switchAuthMode}
            style={{ width: "100%", minHeight: 46, marginTop: 8, border: 0, background: "transparent", color: "var(--muted)", fontSize: 13 }}>
            {signup ? "이미 계정이 있나요? 로그인" : "계정이 없나요? 회원가입"}
          </button>
        </div>
      </Shell>
    );
  }

  // ── 1 언어 선택 ──
  if (step === 1) {
    return (
      <Shell modal={activeModal}>
        <TopBar title="설정" onBack={requestOnboardingExit} right={<ExitButton onClick={requestOnboardingExit} />} />
        <Rail active={0} />
        <div style={{ padding: "4px 26px 18px" }}>
          <h2 style={H2}>사용할 언어를 선택하세요</h2>
          <p style={SUB}>안내와 서류 설명에 사용할 언어예요. 나중에 다시 바꿀 수 있어요.</p>
        </div>
        <div className="scroll" style={{ padding: "0 26px 20px" }}>
          <div className="language-list">
            <LanguageChoice code="KO" title="한국어" subtitle="Korean" selected={lang === "ko"} onClick={() => setLang("ko")} />
            <LanguageChoice code="EN" title="English" subtitle="영어" selected={lang === "en"} onClick={() => setLang("en")} />
          </div>
          <div className="resume-help">같은 계정에 저장된 프로필이 있으면 사진을 다시 등록하지 않고 이어서 진행해요.</div>
        </div>
        <div style={{ padding: "8px 26px 34px" }}>
          {toast && <div role="alert" className="capture-error" style={{ margin: "0 0 10px" }}>{toast}</div>}
          <PrimaryButton disabled={sessionLoading} onClick={resumeSession}>
            {sessionLoading ? "진행 내용 확인 중…" : "계속"}
          </PrimaryButton>
        </div>
      </Shell>
    );
  }

  // ── 2 촬영 ──
  if (step === 2) {
    const uploadPng = async (png) => {
      setCaptureError("");
      setCaptureLoading(true);
      try {
        const page = SCAN_PAGES[scan];
        const data = await uploadAndExtract(png, page.docType);
        const next = { ...shots, [page.key]: png };
        const nextCompletedScans = [...new Set([...completedScans, page.key])];
        setShots(next);
        setCompletedScans(nextCompletedScans);
        setExtract(data);
        if (data.agentResponse) applyAgent(data.agentResponse);
        window.sessionStorage.removeItem(PROFILE_DRAFT_KEY);
        setProfileDraft(Object.fromEntries((data.fields || []).map((field) => [field.key, field.value])));
        setDirtyFields({});
        setProfileErrors({});
        setNat(data?.profile?.nationality || null);
        const empty = SCAN_PAGES.findIndex((page) => !nextCompletedScans.includes(page.key));
        if (empty === -1) {
          go(3);
        } else setScan(empty);
      } catch (error) {
        if (!handleAuthError(error)) setCaptureError(captureMessage(error));
      } finally {
        setCaptureLoading(false);
      }
    };
    const selectImage = async (event) => {
      const source = event.target.files?.[0];
      event.target.value = "";
      if (!source) return;
      try {
        await uploadPng(await convertImageToPng(source));
      } catch (error) {
        setCaptureError(captureMessage(error));
      }
    };
    pastedImageHandlerRef.current = async (source) => {
      try {
        await uploadPng(await convertImageToPng(source));
      } catch (error) {
        setCaptureError(captureMessage(error));
      }
    };
    const takePhoto = async () => {
      try {
        const png = await captureVideoFrameAsPng(videoRef.current, `${SCAN_PAGES[scan].key}.png`);
        stopCamera();
        await uploadPng(png);
      } catch (error) {
        setCaptureError(captureMessage(error));
      }
    };
    const currentShot = shots[SCAN_PAGES[scan].key];
    const currentCompleted = completedScans.includes(SCAN_PAGES[scan].key);
    return (
      <Shell modal={activeModal}>
        <TopBar title="서류 촬영" onBack={() => back(1)} right={<ExitButton onClick={requestOnboardingExit} />} />
        <Rail active={1} />
        <div style={{ padding: "4px 24px 12px" }}>
          <h2 style={H2}>3장을 촬영하세요</h2>
          <p style={SUB}>외국인등록증 앞면·뒷면, 여권 사진면. 카드를 눌러 전환하세요.</p>
        </div>
        <div style={{ padding: "0 24px 14px", display: "flex", gap: 8 }}>
          {SCAN_PAGES.map((p, i) => {
            const done = completedScans.includes(p.key), active = scan === i;
            return (
              <div key={p.key} onClick={() => setScan(i)} className="tap"
                style={{ flex: 1, minHeight: 56, padding: "10px 11px", borderRadius: 12,
                  background: active ? "oklch(0.7 0.13 45 / 0.08)" : done ? "oklch(0.55 0.14 150 / 0.1)" : "oklch(0.95 0.008 60)",
                  border: active ? "1.5px solid var(--brand-2)" : done ? "1px solid oklch(0.55 0.14 150 / 0.4)" : "1px solid var(--line)" }}>
                <div style={{ fontSize: 11.5, fontWeight: 800, color: active ? "oklch(0.5 0.1 45)" : done ? "oklch(0.42 0.12 150)" : "var(--muted)" }}>
                  {done ? "✓ " : ""}{p.label}
                </div>
                <div style={{ fontSize: 10.5, ...mono, color: "var(--muted)", marginTop: 3 }}>{p.sub}</div>
              </div>
            );
          })}
        </div>
        <div style={{ margin: "0 24px", flex: 1, minHeight: 220, borderRadius: 18, background: "oklch(0.18 0.012 60)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, padding: 20 }}>
          {currentShot && (
            <div style={{ width: 40, height: 40, borderRadius: 99, background: "var(--ok)", color: "#fff", fontSize: 20, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>✓</div>
          )}
          <div className="scan-preview">
            {cameraStarting
              ? <div className="camera-starting" role="status">카메라 권한을 확인하는 중이에요.<small>브라우저 팝업에서 ‘허용’을 눌러 주세요.</small></div>
              : cameraOpen
              ? <video ref={videoRef} autoPlay playsInline muted aria-label={`${SCAN_PAGES[scan].label} 카메라 미리보기`} />
              : currentShot
              ? <ImagePreview file={currentShot} alt={`${SCAN_PAGES[scan].label} 촬영 미리보기`} />
              : currentCompleted
              ? <div className="saved-scan"><span>✓</span><b>이전에 등록한 사진이에요</b><small>서버에 인식 결과가 저장되어 있어 다시 촬영하지 않아도 돼요.</small></div>
              : <div style={{ ...mono, fontSize: 11, color: "oklch(0.7 0.01 60)", textAlign: "center" }}>{SCAN_PAGES[scan].label}</div>}
          </div>
          <div style={{ alignSelf: "stretch", ...mono, fontSize: 10.5, color: "var(--ok)" }}>●&nbsp; {cameraStarting ? "카메라 권한 대기 중" : cameraOpen ? "카메라 준비됨" : currentShot ? "PNG 변환 완료" : currentCompleted ? "이전 등록 완료" : "촬영하기를 누르면 카메라가 열려요"}</div>
        </div>
        {captureError && <div role="alert" className="capture-error">{captureError} <button type="button" onClick={() => nativeCameraInputRef.current?.click()}>기기 카메라로 열기</button></div>}
        <div style={{ margin: "12px 24px 0", padding: "10px 13px", borderRadius: 12, background: "oklch(.93 .008 60)", fontSize: 11.5, lineHeight: 1.5, color: "var(--muted)" }}>이미지를 복사했다면 <b>Cmd+V</b> 또는 <b>Ctrl+V</b>로 붙여넣을 수 있어요.<br />재학증명서는 사진 촬영 없이 종이 원본만 준비하면 돼요.</div>
        <div style={{ padding: "16px 24px 34px", display: "flex", gap: 12 }}>
          <input ref={fileInputRef} type="file" accept="image/*" onChange={selectImage} hidden />
          <input ref={nativeCameraInputRef} type="file" accept="image/*" capture="environment" onChange={selectImage} hidden />
          <div style={{ flex: 1 }}><PrimaryButton disabled={captureLoading || cameraStarting} onClick={cameraOpen ? takePhoto : () => startCamera(true)}>{captureLoading ? "업로드·인식 중…" : cameraStarting ? "카메라 연결 중…" : cameraOpen ? "사진 찍기" : currentShot || currentCompleted ? "이 장 다시 등록" : "촬영하기"}</PrimaryButton></div>
          <button type="button" disabled={captureLoading || cameraStarting} onClick={cameraOpen ? stopCamera : () => fileInputRef.current?.click()} className="file-attach tap">{cameraOpen ? "닫기" : "파일 첨부"}</button>
        </div>
      </Shell>
    );
  }

  // ── 3 프로필 만들기 (OCR 확인) ──
  if (step === 3) {
    const fields = extract?.fields || [];
    const updateField = (field, value) => {
      if (!field.editable) return;
      setProfileDraft((current) => ({ ...current, [field.key]: value }));
      setDirtyFields((current) => {
        const next = { ...current };
        if (value === field.value) delete next[field.key];
        else next[field.key] = value;
        return next;
      });
      setProfileErrors((current) => {
        const next = { ...current };
        delete next[field.key];
        return next;
      });
    };
    const submitProfile = async () => {
      setProfileSubmitting(true);
      setProfileErrors({});
      try {
        const response = await confirmProfile(sessionId || extract?.state?.session_id, dirtyFields);
        applyAgent(response);
        setExtract((current) => ({
          ...current,
          profile: response.state?.profile || {},
          state: response.state || {},
          agentResponse: response,
        }));
        setDirtyFields({});
        window.sessionStorage.removeItem(PROFILE_DRAFT_KEY);
        // 다음 UI 가 질문이면 상담 화면, 그 밖이면 과제 목록으로 간다.
        go(readUi(response).type === "question" ? 4 : 5);
      } catch (error) {
        if (handleAuthError(error)) return;
        if (error?.status === 422 && error?.code === "validation_failed") {
          const details = error.details;
          const entries = Array.isArray(details)
            ? details.map((detail) => [detail.field, detail.reason || error.message])
            : Object.entries(details || {}).map(([field, reason]) => [field, String(reason)]);
          setProfileErrors(Object.fromEntries(entries.filter(([field]) => field && field !== "message")));
        }
        if (!error?.details || Object.keys(error.details).length === 0) {
          setProfileErrors({ _form: error instanceof Error ? error.message : "프로필을 확인하지 못했어요." });
        }
      } finally {
        setProfileSubmitting(false);
      }
    };
    return (
      <Shell modal={activeModal}>
        <TopBar title="프로필 만들기" onBack={() => back(2)} right={<ExitButton onClick={requestOnboardingExit} />} />
        <Rail active={2} />
        <div style={{ padding: "4px 24px 14px" }}>
          <h2 style={H2}>카드에서 만든 프로필</h2>
          <p style={SUB}>노란색 항목을 확인하고, 잘못 읽은 값만 수정해 주세요.</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 9 }}>
          <Label>OCR 추출 결과</Label>
          {fields.map((field) => (
            <Field key={field.key} label={field.label} value={profileDraft[field.key] ?? field.value}
              confidence={field.confidence} editable={field.editable} dirty={field.key in dirtyFields}
              error={profileErrors[field.key]} onChange={(value) => updateField(field, value)} />
          ))}
          {profileErrors._form && <div role="alert" className="capture-error" style={{ margin: 0 }}>{profileErrors._form}</div>}
        </div>
        <div style={{ padding: "14px 24px 34px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45 }}>수정 불가 항목은 마스킹된 값으로 전송되지 않아요.</div>
          <PrimaryButton disabled={profileSubmitting || fields.length === 0} onClick={submitProfile}>
            {profileSubmitting ? "확인 중…" : "확인하고 계속"}
          </PrimaryButton>
        </div>
      </Shell>
    );
  }

  // ── 4 AI 상담 (서버가 내려주는 question 을 그린다) ──
  if (step === 4) {
    const hasPurpose = Object.values(answers.purposes).some(Boolean);
    const updatePhone = (phone) => { setAnswers((value) => ({ ...value, phone })); setVerdict(null); };
    const updateCert = (cert) => { setAnswers((value) => ({ ...value, cert })); setVerdict(null); };
    const togglePurpose = (index) => {
      setAnswers((value) => ({ ...value, purposes: { ...value.purposes, [index]: !value.purposes[index] } }));
      setVerdict(null);
    };
    const runVerdict = async () => {
      setChatLoading(true);
      const scenario = new URLSearchParams(window.location.search).get("scenario");
      setVerdict(await getVerdict("mock", { ...answers, scenario }));
      setChatLoading(false);
    };

    if (verdict) {
      const editAnswers = () => setVerdict(null);
      return (
        <Shell modal={activeModal}>
          <TopBar title="첫계좌 AI" onBack={editAnswers} right={<span className="review-status"><i />심사 완료</span>} />
          <Rail active={3} />
          <div className="scroll review-scroll">
            <section className="review-hero">
              <div className="review-kicker">계좌&nbsp;&nbsp;개설&nbsp;&nbsp;진단&nbsp;&nbsp;결과</div>
              <h1>{verdict.headline}</h1>
              <p>{verdict.summary}</p>
            </section>

            <div className="review-content">
              {verdict.blocker && (
                <section className="review-card blocker">
                  <div className="review-card-head"><b>{verdict.blocker.title}</b><span>{verdict.blocker.badge}</span></div>
                  <p>{verdict.blocker.body}</p>
                </section>
              )}
              <AccountCard title="한도제한계좌" subtitle="한도제한계좌 · 1일 이체 100만원 한도" account={verdict.limited} />
              <AccountCard title="일반계좌" subtitle="일반계좌" account={verdict.regular} />

              <details className="review-sources">
                <summary>판정 근거</summary>
                {verdict.sources.map((source) => <div key={source}>· {source}</div>)}
              </details>
              <p className="review-disclaimer">이 판정은 은행 정책 기준의 사전 점검입니다. 최종 계좌 개설 여부는 은행이 결정합니다.</p>
            </div>
          </div>
          <div className="review-actions">
            <button type="button" onClick={editAnswers} className="review-edit tap">답변 수정</button>
            <button type="button" onClick={() => go(6)} className="review-next tap">{verdictCta(verdict.kind)}</button>
          </div>
        </Shell>
      );
    }


    const question = ui.type === "question" ? ui.payload : null;
    const options = question ? questionOptions(question) : [];

    // 답변은 항상 POST /api/chat 의 message 로 간다. 응답의 ui.type 이 다음 화면을 정한다.
    const answer = async (value) => {
      if (chatLoading || !value) return;
      setChatLoading(true);
      setToast("");
      setMessages((current) => [...current, { from: "user", text: value }]);
      try {
        const response = applyAgent(await sendChat(sessionId, value));
        setChatInput("");
        const next = readUi(response).type;
        if (next !== "question") go(5);      // 질문이 끝나면 과제 목록으로
      } catch (error) {
        if (!handleAuthError(error)) setToast(error?.message || "메시지를 보내지 못했어요.");
      } finally {
        setChatLoading(false);
      }
    };

    return (
      <Shell modal={activeModal}>
        <TopBar title="첫계좌 AI" onBack={() => back(3)} right={<span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--ok)", fontSize: 11.5 }}><span style={{ width: 7, height: 7, borderRadius: 99, background: "var(--ok)" }} />상담 중</span>} />
        <Rail active={3} />
        <div className="scroll chat-scroll" style={{ padding: "6px 18px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          {messages.map((message, index) => (
            <ChatBubble key={`${message.from}-${index}`} mine={message.from === "user"} avatar={message.from === "agent"}>
              {message.text}
            </ChatBubble>
          ))}

          {question && (
            <ChatBubble avatar wide>
              <QuestionCard payload={question} options={options} value={chatInput}
                onChange={setChatInput} onSubmit={answer} disabled={chatLoading} />
            </ChatBubble>
          )}

          {/* 모르는 ui.type 이면 reply 만 보여주고 다음 화면으로 넘어갈 길을 남긴다 */}
          {!question && !chatLoading && (
            <button type="button" onClick={() => go(5)} className="chat-submit tap">할 일 목록 보기</button>
          )}

          {chatLoading && <ChatBubble avatar>답변을 정리하고 있어요…</ChatBubble>}
          {toast && <div role="alert" className="capture-error" style={{ margin: 0 }}>{toast}</div>}

          <div ref={chatEndRef} aria-hidden="true" />
        </div>
      </Shell>
    );
  }

  // ── 5 할 일 / 과제 선택 ──
  if (step === 5) {
    const tasks = agentState?.tasks || [];
    const startTask = async (task) => {
      if (taskBusy) return;
      setTaskBusy(task.id);
      setToast("");
      try {
        const response = applyAgent(await startAction(sessionId, task.id));
        // 다음 질문이 오면 상담 화면으로 되돌아간다. 그 밖의 ui 는 담당 파트(6~9)가 그린다.
        if (readUi(response).type === "question") go(4);
      } catch (error) {
        // 409 prerequisite_missing 은 상태를 바꾸지 않고 토스트만 띄운다.
        if (!handleAuthError(error)) setToast(error?.message || "과제를 시작하지 못했어요.");
      } finally {
        setTaskBusy("");
      }
    };
    return (
      <Shell modal={activeModal}>
        <TopBar title="할 일" onBack={() => back(4)} />
        <Rail active={3} />
        <div style={{ padding: "4px 24px 14px" }}>
          <h2 style={H2}>지금 할 수 있는 일</h2>
          <p style={SUB}>잠긴 항목은 먼저 끝내야 하는 과제가 있어요.</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
          {tasks.length === 0 && (
            <div style={{ ...card, fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5 }}>
              아직 받은 과제가 없어요. 상담을 이어가면 목록이 채워져요.
            </div>
          )}
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} busy={taskBusy === task.id} onStart={startTask} />
          ))}
        </div>
        <div style={{ padding: "10px 24px 34px", display: "flex", flexDirection: "column", gap: 10 }}>
          {toast && <div role="alert" className="capture-error" style={{ margin: 0 }}>{toast}</div>}
          <PrimaryButton onClick={() => go(4)}>상담으로 돌아가기</PrimaryButton>
          {/* 화면 6~9(서류·승인·이력)로 들어가는 유일한 진입로다. */}
          <button type="button" onClick={() => go(7)} className="tap"
            style={{ width: "100%", minHeight: 46, borderRadius: 12, border: "1px solid var(--line)",
              background: "#fff", fontSize: 13.5, fontWeight: 700, color: "oklch(0.25 0.012 60)" }}>
            내 신청서 · 서류함
          </button>
        </div>
      </Shell>
    );
  }

  // ── 6 준비 안내 ──
  if (step === 6 && verdict)
    return (
      <Shell modal={activeModal}>
        <TopBar title="준비할 것" onBack={() => back(4)} />
        <Rail active={4} />
        <div style={{ padding: "4px 24px 16px" }}>
          <div style={{ padding: 17, borderRadius: 16, background: "#c44f40", color: "#fff" }}>
            <div style={{ ...mono, fontSize: 10.5, letterSpacing: "0.12em", textTransform: "uppercase", opacity: 0.85, marginBottom: 8 }}>다음 할 일</div>
            <div style={{ fontSize: 17, fontWeight: 800, lineHeight: 1.3 }}>{nextAction(verdict).title}</div>
            <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 8, opacity: 0.92 }}>{nextAction(verdict).meta}</div>
          </div>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ ...card, padding: 16 }}>
            <div style={{ fontSize: 15, fontWeight: 800 }}>{nextAction(verdict).cardTitle}</div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 2 }}>{nextAction(verdict).cardMeta}</div>
            <div style={{ marginTop: 11, display: "flex", flexDirection: "column", gap: 9 }}>
              {nextAction(verdict).steps.map((s, i) => (
                <div key={i} style={{ display: "flex", gap: 10, fontSize: 12.5, lineHeight: 1.45, color: "oklch(0.35 0.012 60)" }}>
                  <span style={{ ...mono, color: "#c44f40", fontWeight: 700 }}>{i + 1}</span><span>{s}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 12, padding: "9px 11px", borderRadius: 9, background: "oklch(.93 .008 60)", fontSize: 11.5, lineHeight: 1.45 }}>{nextAction(verdict).note}</div>
          </div>
        </div>
        <div style={{ padding: "16px 24px 34px" }}>
          <PrimaryButton onClick={() => go(7)}>내 신청서</PrimaryButton>
        </div>
      </Shell>
    );

  // ── 7 신청서 ──
  if (step === 7)
    return (
      <Shell modal={activeModal}>
        <TopBar title="내 신청서" onBack={() => back(verdict ? 6 : 5)} />
        <div style={{ padding: "4px 24px 16px" }}>
          <Rail active={4} />
          <h2 style={H2}>채워진 신청서 {documents.length}종</h2>
          <p style={SUB}>인쇄하거나 창구에서 휴대폰으로 보여주세요.</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          {documents.length === 0 && (
            <div style={{ ...card, display: "flex", gap: 13 }}>
              <div style={{ width: 62, height: 84, flex: "none", borderRadius: 7, border: "1px solid oklch(0.88 0.01 60)", background: "repeating-linear-gradient(0deg, oklch(0.9 0.01 60) 0 3px, oklch(0.97 0.008 60) 3px 9px)" }} />
              <div style={{ flex: 1 }}>
                <b style={{ fontSize: 14.5 }}>계좌개설신청서</b>
                <div style={{ marginTop: 10, fontSize: 11, color: "var(--muted)", lineHeight: 1.4 }}>미리보기를 누르면 AI가 신청서를 생성합니다.</div>
              </div>
            </div>
          )}
          {documents.map((d) => (
            <div key={d.id} style={{ ...card, display: "flex", gap: 13 }}>
              <div style={{ width: 62, height: 84, flex: "none", borderRadius: 7, border: "1px solid oklch(0.88 0.01 60)", background: "repeating-linear-gradient(0deg, oklch(0.9 0.01 60) 0 3px, oklch(0.97 0.008 60) 3px 9px)" }} />
              <div style={{ flex: 1 }}>
                <b style={{ fontSize: 14.5 }}>{d.title}</b>
                <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "'Noto Sans KR',sans-serif" }}>{formatDate(d.created_at)}</div>
                <button type="button" onClick={() => openStoredDocument(d)} className="tap" style={{ marginTop: 10, padding: 0, border: 0, background: "transparent", color: "var(--brand-2)", fontSize: 11.5, fontWeight: 700 }}>저장된 PDF 보기</button>
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: "16px 24px 34px" }}>
          {previewError && <div role="alert" className="capture-error" style={{ margin: "0 0 10px" }}>{previewError}</div>}
          <PrimaryButton disabled={previewLoading} onClick={openPdfPreview}>
            {previewLoading ? "PDF 생성 중…" : "PDF 미리보기"}
          </PrimaryButton>
          <button type="button" onClick={() => go(9)} className="tap" style={{ width: "100%", marginTop: 9, minHeight: 46, borderRadius: 12, border: "1px solid var(--line)", background: "#fff", fontWeight: 700 }}>내 서류함 · 실행 이력</button>
        </div>
      </Shell>
    );

  // ── 9 내 서류함 / 실행 이력 ──
  if (step === 9)
    return (
      <Shell modal={activeModal}>
        <TopBar title="내 서류함 · 실행 이력" onBack={() => back(7)} />
        <div className="scroll" style={{ padding: "4px 20px 24px", display: "flex", flexDirection: "column", gap: 18 }}>
          <section>
            <h2 style={{ ...H2, fontSize: 20 }}>저장 문서</h2>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 9 }}>
              {documents.length === 0 && <div style={{ ...card, color: "var(--muted)", fontSize: 12.5 }}>최근 응답에 저장된 문서가 없습니다.</div>}
              {documents.map((document) => (
                <div key={document.id} style={card}>
                  <b style={{ fontSize: 14 }}>{document.title}</b>
                  <div style={{ marginTop: 4, color: "var(--muted)", fontSize: 11.5 }}>{formatDate(document.created_at)}</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <button type="button" onClick={() => openStoredDocument(document)} className="tap" style={smallActionStyle}>미리보기</button>
                    <button type="button" onClick={() => downloadPdf(document)} className="tap" style={smallActionStyle}>PDF 다운로드</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h2 style={{ ...H2, fontSize: 20 }}>실행 이력</h2>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 9 }}>
              {ledgerLoading && <div style={{ ...card, color: "var(--muted)", fontSize: 12.5 }}>불러오는 중…</div>}
              {ledgerError && <div role="alert" className="capture-error" style={{ margin: 0 }}>{ledgerError}</div>}
              {!ledgerLoading && !ledgerError && ledger.length === 0 && <div style={{ ...card, color: "var(--muted)", fontSize: 12.5 }}>아직 승인 후 실행된 작업이 없습니다.</div>}
              {ledger.map((entry, index) => (
                <div key={`${entry.action || "action"}-${entry.approved_at || index}`} style={card}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><b>{entry.action || "실행 작업"}</b><span style={{ ...mono, color: "var(--brand-2)", fontSize: 10.5 }}>{entry.risk_level}</span></div>
                  <div style={{ marginTop: 6, color: "var(--muted)", fontSize: 11.5 }}>{formatDate(entry.approved_at)}</div>
                  {(entry.evidence || []).map((item) => <div key={item} style={{ marginTop: 6, fontSize: 11.5, color: "var(--muted)" }}>근거 · {item}</div>)}
                </div>
              ))}
            </div>
          </section>
        </div>
        {previewError && <div role="alert" className="capture-error" style={{ margin: "0 20px 12px" }}>{previewError}</div>}
      </Shell>
    );

  // ── PDF 뷰어 ──
  if (step === 10 && preview && previewBlobUrl)
    return (
      <Shell modal={activeModal} dark>
        <TopBar title={preview.title} onBack={() => back(9)} />
        {(preview.warnings || []).length > 0 && (
          <div role="alert" style={{ margin: "0 20px 12px", padding: "11px 13px", borderRadius: 11, background: "oklch(.8 .1 75 / .15)", color: "oklch(.82 .08 75)", fontSize: 11.5, lineHeight: 1.5 }}>
            {preview.warnings.map((warning) => <div key={warning}>⚠ {warning}</div>)}
          </div>
        )}
        <div className="scroll" style={{ padding: "0 20px 20px" }}>
          <iframe title={preview.title} src={previewBlobUrl} style={{ width: "100%", height: "100%", minHeight: 620, border: 0, borderRadius: 6, background: "#fff" }} />
        </div>
        <div style={{ padding: "16px 20px 34px", display: "flex", gap: 9 }}>
          <button type="button" onClick={() => downloadPdf(preview)} className="tap" style={{ ...smallActionStyle, minHeight: 52, color: "#fff", background: "var(--brand-2)" }}>PDF 다운로드</button>
        </div>
      </Shell>
    );

  return (
    <Shell modal={activeModal}>
      <TopBar title="첫계좌" onBack={() => back(0)} />
      <div style={{ padding: "28px 26px", display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 style={H2}>화면을 다시 연결할게요</h2>
        <p style={SUB}>진행 내용은 임시 저장되어 있어요. 이어하기를 눌러 안전하게 돌아가세요.</p>
        <PrimaryButton disabled={sessionLoading} onClick={resumeSession}>
          {sessionLoading ? "불러오는 중…" : "저장된 진행 이어하기"}
        </PrimaryButton>
      </div>
    </Shell>
  );
}

// ── 작은 헬퍼 컴포넌트 ──
function Shell({ children, dark, modal }) {
  return (
    <div className="app-shell">
      <div className="phone" style={dark ? { background: "oklch(0.22 0.012 60)" } : undefined}>{children}{modal}</div>
    </div>
  );
}
function Label({ children }) {
  return <div style={{ padding: "6px 0", ...mono, fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)" }}>{children}</div>;
}
function ImagePreview({ file, alt }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const nextUrl = URL.createObjectURL(file);
    setUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);
  return url ? <img src={url} alt={alt} /> : null;
}
function AuthInput({ label, type = "text", value, onChange, placeholder, ...inputProps }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 7 }}>
      <span style={{ fontSize: 12.5, fontWeight: 700 }}>{label}</span>
      <input className="auth-input" type={type} value={value} onChange={onChange} placeholder={placeholder} {...inputProps}
        style={{ width: "100%", height: 54, border: "1px solid var(--line)", borderRadius: 13, padding: "0 15px", outline: "none", background: "#fff", color: "var(--ink)", font: "inherit", fontSize: 15 }} />
    </label>
  );
}
function FieldHint({ children, tone = "info" }) {
  return <div className={`auth-field-hint ${tone}`}>{children}</div>;
}
function ChatBubble({ children, mine, avatar, wide }) {
  return (
    <div className={`chat-line${mine ? " mine" : ""}${wide ? " wide" : ""}`}>
      {avatar && <BridgeMark size={32} />}
      <div className="chat-bubble">{children}</div>
    </div>
  );
}
function ChatOptions({ children, wrap }) {
  return <div className={`chat-options${wrap ? " wrap" : ""}`}>{children}</div>;
}
function ChatChoice({ children, selected, onClick }) {
  return <button type="button" onClick={onClick} className={`chat-choice tap${selected ? " selected" : ""}`}>{selected && <span>✓</span>}{children}</button>;
}
function AccountCard({ title, subtitle, account }) {
  return (
    <section className={`review-card account${account.ready ? " ready" : ""}`}>
      <div className="review-card-head"><b>{title}</b><span>{account.status}</span></div>
      <div className="review-card-sub">{subtitle}</div>
      <p>{account.body}</p>
    </section>
  );
}
function Row2({ children }) {
  return <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9, marginBottom: 10 }}>{children}</div>;
}
function ExitButton({ onClick }) {
  return <button type="button" onClick={onClick} className="exit-button">나가기</button>;
}
function LanguageChoice({ code, title, subtitle, selected, onClick }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={selected} className={`language-choice${selected ? " selected" : ""}`}>
      <span className="language-code" aria-hidden="true">{code}</span>
      <span className="language-copy"><b>{title}</b><small>{subtitle}</small></span>
      <span className="language-check" aria-hidden="true">{selected ? "✓" : ""}</span>
    </button>
  );
}
function Pick({ children, on, ok, onClick }) {
  const accent = ok ? "var(--ok)" : "var(--brand-2)";
  const tint = ok ? "oklch(0.55 0.14 150 / 0.09)" : "oklch(0.7 0.13 45 / 0.08)";
  return (
    <div onClick={onClick} className="tap"
      style={{ minHeight: 52, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 13, fontSize: 14.5, fontWeight: on ? 700 : 600,
        border: on ? `1.5px solid ${accent}` : "1px solid oklch(0.88 0.01 60)", background: on ? tint : "#fff", fontFamily: "'Noto Sans KR',sans-serif" }}>
      {children}
    </div>
  );
}
function ExitConfirmModal({ onContinue, onExit }) {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="exit-title" className="modal-backdrop">
      <div className="exit-dialog">
        <div className="exit-dialog-icon" aria-hidden="true">☁</div>
        <h3 id="exit-title">진행을 잠시 멈출까요?</h3>
        <p>사진 자체는 브라우저에 보관하지 않고, 진행 단계만 이 기기에 임시 저장해요. 다음에 로그인하면 서버에 저장된 프로필로 이어갈 수 있어요.</p>
        <div className="exit-dialog-actions">
          <button type="button" onClick={onContinue} className="tap">계속 진행</button>
          <button type="button" onClick={onExit} className="tap primary">저장하고 나가기</button>
        </div>
      </div>
    </div>
  );
}
function ApprovalModal({ approval, loading, error, onDecision }) {
  return (
    <div role="dialog" aria-modal="true" aria-label="실행 승인" style={{ position: "absolute", inset: 0, zIndex: 20, background: "oklch(0.2 0.012 60 / 0.55)", display: "flex", alignItems: "flex-end" }}>
      <div style={{ width: "100%", padding: "22px 20px 30px", borderRadius: "24px 24px 0 0", background: "#fff" }}>
        <div style={{ ...mono, color: "var(--brand-2)", fontSize: 10.5, fontWeight: 800, letterSpacing: ".1em" }}>APPROVAL · {approval.risk_level || "L2"}</div>
        <h3 style={{ margin: "10px 0 8px", fontSize: 20 }}>{approval.title || "실행 승인"}</h3>
        {(approval.summary || []).map((item) => <div key={item} style={{ padding: "7px 0", fontSize: 12.5 }}>· {item}</div>)}
        {(approval.evidence || []).length > 0 && <div style={{ marginTop: 10, fontSize: 11.5, color: "var(--muted)" }}>근거</div>}
        {(approval.evidence || []).map((item) => <div key={item} style={{ padding: "4px 0", fontSize: 11.5, color: "var(--muted)" }}>· {item}</div>)}
        <p style={{ margin: "12px 0", color: "var(--muted)", fontSize: 11.5, lineHeight: 1.5 }}>아직 외부 예약이나 제출은 실행되지 않았습니다.</p>
        {error && <div role="alert" className="capture-error" style={{ margin: "0 0 10px" }}>{error}</div>}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
          <button type="button" disabled={loading} onClick={() => onDecision(false)} className="tap" style={{ minHeight: 50, borderRadius: 13, border: "1px solid var(--line)", background: "#fff", fontWeight: 700 }}>취소</button>
          <button type="button" disabled={loading} onClick={() => onDecision(true)} className="tap" style={{ minHeight: 50, borderRadius: 13, border: 0, background: "var(--brand-2)", color: "#fff", fontWeight: 700 }}>{loading ? "처리 중…" : "확인"}</button>
        </div>
      </div>
    </div>
  );
}

const smallActionStyle = { flex: 1, minHeight: 38, borderRadius: 10, border: "1px solid var(--line)", background: "#fff", fontSize: 11.5, fontWeight: 700 };

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("ko-KR");
}
function Sheet({ children, title, onClose }) {
  return (
    <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "oklch(0.2 0.012 60 / 0.45)", display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: "26px 26px 34px 34px", padding: "18px 14px 26px", maxHeight: "74%", overflow: "auto" }}>
        <div style={{ padding: "0 10px 12px", fontSize: 16, fontWeight: 800 }}>{title}</div>
        {children}
      </div>
    </div>
  );
}

// 촬영 화면 오류 문구. 계약의 error code 별로 다음 행동을 다르게 안내한다.
function captureMessage(error) {
  switch (error?.code) {
    case "extraction_failed":
      return "사진에서 정보를 읽지 못했어요. 빛 반사를 피해 카드 전체가 보이게 다시 촬영해 주세요.";
    case "unsupported_media_type":
      return "PNG 이미지만 올릴 수 있어요. 다시 촬영하면 자동으로 PNG로 변환돼요.";
    case "upload_not_completed":
      return "사진 업로드가 끝나지 않았어요. 다시 촬영해 주세요.";
    case "network":
      return "네트워크에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.";
    default:
      return error instanceof Error ? error.message : "이미지를 처리하지 못했어요.";
  }
}

function mask(arc) {
  if (!arc) return "";
  return arc.slice(0, 8) + "••••••";
}
function verdictCta(kind) {
  return {
    ready: "무엇을 가져가나요?",
    passport: "어떻게 재발급하나요?",
    phone: "휴대폰은 어떻게 개통하나요?",
    cert: "어디서 떼나요?",
  }[kind] || "다음 단계 보기";
}
function nextAction(v) {
  if (v.kind === "passport")
    return { title: "은행 방문 전에 여권을 재발급하세요", meta: "주한 대사관 · 1~3주 · 외국인등록증 영향 없음",
      cardTitle: "여권 재발급", cardMeta: "기존 여권 · 외국인등록증 · 대사관 방문",
      note: "새 여권이 나오면 다시 앱으로 오세요. 서류를 다시 채워드려요.",
      steps: ["주한 대사관에 방문 예약을 하세요.", "외국인등록증과 기존 여권을 지참하세요.", "새 번호가 나오면 다시 앱으로 오세요 — 서류를 다시 채워드려요."] };
  if (v.kind === "phone")
    return { title: "본인 명의 선불 휴대폰을 개통하세요", meta: "아무 통신사 매장 · 외국인등록증+여권 지참 · 월 15,000원부터 · 당일 개통",
      cardTitle: "휴대폰 개통", cardMeta: "본인 명의 개통 · 알뜰폰 선불 가능",
      note: "친구 명의 번호는 사용할 수 없어요. 반드시 본인 명의여야 해요.",
      steps: ["외국인등록증과 여권을 들고 아무 통신사 매장에 가세요.", "선불 요금제를 요청하세요 — 한국 계좌 없어도 돼요.", "반드시 본인 명의여야 해요. 당일 개통돼요."] };
  if (v.kind === "cert")
    return { title: "재학증명서를 인쇄하세요", meta: "학교 포털 또는 국제처 · 종이 원본 · 발급 3개월 이내",
      cardTitle: "재학증명서", cardMeta: "재학증명서 또는 입학허가서 · 학교 발급",
      note: "이 서류는 읽지 않아요. 종이만 챙기면 창구에서 확인해요.",
      steps: ["학교 포털에 로그인해 인쇄하세요.", "아직 재학 전인가요? 입학허가서로 대신할 수 있어요.", "종이 원본만 가능 — 창구에서 사본을 보관해요."] };
  return { title: "서류를 들고 은행에 방문하세요", meta: "외국인등록증, 여권, 재학증명서, 인쇄한 신청서",
    cardTitle: "재학증명서", cardMeta: "재학증명서 또는 입학허가서 · 학교 발급",
    note: "이 서류는 읽지 않아요. 종이만 챙기면 창구에서 확인해요.",
    steps: ["학교 포털에서 인쇄하거나 국제처에 문의하세요.", "종이 원본만 가능해요. 발급 3개월 이내여야 해요.", "아직 재학 전인가요? 입학허가서로 대신할 수 있어요."] };
}
