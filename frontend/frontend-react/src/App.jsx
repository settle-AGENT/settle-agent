import React, { useEffect, useRef, useState } from "react";
import { BridgeMark, TopBar, Rail, PrimaryButton, Field, QuestionCard, TaskCard } from "./components.jsx";
import {
  signUp, login, uploadAndExtract, confirmProfile, previewAction, approveAction, getLedger,
  fetchDocument, nationalityLabel,
  createSession, sendChatStream, startAction, readUi, questionOptions, clearToken, readMemberId,
} from "./api.js";
import { captureVideoFrameAsPng, convertImageToPng } from "./image.js";

const SCAN_PAGES = [
  { key: "arcFront", docType: "arc_front", ko: ["외국인등록증 앞면", "앞면"], en: ["Residence card front", "Front"] },
  { key: "arcBack", docType: "arc_back", ko: ["외국인등록증 뒷면", "뒷면"], en: ["Residence card back", "Back"] },
  { key: "passport", docType: "passport", ko: ["여권", "여권 사진면"], en: ["Passport", "Photo page"] },
];
const APPLICATIONS = {
  alien_registration: { ko: "통합신청서 · 외국인등록", en: "Integrated application · Registration" },
  residence_change: { ko: "통합신청서 · 체류지 변경", en: "Integrated application · Address change" },
  work_activity: { ko: "통합신청서 · 체류자격외활동", en: "Integrated application · Activity permit" },
  open_bank_account: { ko: "계좌개설신청서", en: "Bank account application" },
};
const APPLICATION_GOALS = {
  alien_registration: { ko: "목표: 외국인등록 · 출입국·외국인청 제출용", en: "Goal: Alien registration · for the immigration office" },
  residence_change: { ko: "목표: 체류지 변경 신고 · 출입국·외국인청 제출용", en: "Goal: Address change · for the immigration office" },
  work_activity: { ko: "목표: 체류자격외활동 허가 · 출입국·외국인청 제출용", en: "Goal: Activity permit · for the immigration office" },
  open_bank_account: { ko: "목표: 계좌 개설 · 은행 영업점 제출용", en: "Goal: Open an account · for the bank branch" },
};
const ONBOARDING_PROGRESS_KEY = "settle_onboarding_progress_v1";
const SESSION_DRAFTS_KEY = "settle_session_drafts_v1";
const UI_LANGUAGE_VERSION = 2;
const PROFILE_DRAFT_KEY = "settle_profile_draft_v1";
const EMPTY_AUTH = { email: "", password: "", passwordConfirm: "" };
const EMPTY_ANSWERS = { phone: null, cert: null, purposes: {} };
const PROFILE_LABELS = {
  name_en: "이름", arc_no: "등록번호", nationality: "국적", visa_type: "체류자격",
  stay_expiry: "체류기간", addr_kr: "체류지", birth_date: "생년월일", gender: "성별",
};
const GENDER_LABELS = { F: ["여성", "Female"], M: ["남성", "Male"] };
const REUSABLE_PROFILE_KEYS = ["name_en", "arc_no", "nationality", "visa_type", "stay_expiry"];

const EMAIL_PATTERN = /^(?=.{1,64}@)[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+\/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z]{2,63})+$/;

function readOnboardingProgress() {
  try {
    const progress = JSON.parse(window.localStorage.getItem(ONBOARDING_PROGRESS_KEY) || "null");
    if (!progress || typeof progress !== "object") return null;
    return {
      lang: progress.uiLanguageVersion === UI_LANGUAGE_VERSION && progress.lang === "en" ? "en" : "ko",
      lastStep: Number.isInteger(progress.lastStep) ? progress.lastStep : 1,
      currentStep: Number.isInteger(progress.currentStep)
        ? progress.currentStep
        : Number.isInteger(progress.lastStep) ? progress.lastStep : 1,
      completedScans: Array.isArray(progress.completedScans)
        ? progress.completedScans.filter((key) => SCAN_PAGES.some((page) => page.key === key))
        : [],
      answers: progress.answers && typeof progress.answers === "object"
        ? { ...EMPTY_ANSWERS, ...progress.answers, purposes: progress.answers.purposes || {} }
        : { ...EMPTY_ANSWERS },
      updatedAt: progress.updatedAt || null,
      memberId: typeof progress.memberId === "string" ? progress.memberId : "",
      sessionId: typeof progress.sessionId === "string" ? progress.sessionId : "",
    };
  } catch {
    return null;
  }
}

function readSessionDrafts(expectedMemberId = "") {
  try {
    const drafts = JSON.parse(window.localStorage.getItem(SESSION_DRAFTS_KEY) || "[]");
    if (!Array.isArray(drafts)) return [];
    return drafts.filter((draft) => draft && typeof draft.sessionId === "string"
      && (!expectedMemberId || draft.memberId === expectedMemberId));
  } catch {
    return [];
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

function passwordChecks(password, locale = "ko") {
  const en = locale === "en";
  return [
    { label: en ? "8–64 characters" : "8~64자", met: password.length >= 8 && password.length <= 64 },
    { label: en ? "Includes a letter" : "영문 포함", met: /[A-Za-z]/.test(password) },
    { label: en ? "Includes a number" : "숫자 포함", met: /\d/.test(password) },
    { label: en ? "Includes a special character" : "특수문자 포함", met: /[^A-Za-z0-9]/.test(password) },
  ];
}

function authErrorMessage(error, locale = "ko") {
  const en = locale === "en";
  if (error?.code === "EMAIL_ALREADY_EXISTS") {
    return en ? "This email is already registered. Sign in or use another email." : "이미 가입된 이메일이에요. 로그인하거나 다른 이메일을 사용해 주세요.";
  }
  if (error?.code === "INVALID_CREDENTIALS") {
    return en ? "Check your email and password." : "이메일 또는 비밀번호를 확인해 주세요.";
  }
  const validationReasons = Array.isArray(error?.details)
    ? [...new Set(error.details.map((detail) => detail?.reason).filter(Boolean))]
    : [];
  if (error?.code === "validation_failed" && validationReasons.length) {
    return en ? "Check the information you entered." : validationReasons.join(" ");
  }
  return localizedError(error, locale, "인증 요청을 처리하지 못했어요.", "Could not process the authentication request.");
}

function resumeDetails(state, currentUi, locale = "ko") {
  if (!state?.session_id) return null;
  const en = locale === "en";
  const tasks = Array.isArray(state.tasks) ? state.tasks : [];
  const pendingActionId = state.pending_approval?.action_id;
  const pendingTask = tasks.find((task) => task.id === pendingActionId);
  const activeTask = pendingTask || tasks.find((task) => task.status === "in_progress");
  const title = activeTask?.label || APPLICATIONS[pendingActionId]?.[locale];

  if (state.pending_approval) {
    return {
      title: title || (en ? "Document application" : "서류 신청"),
      stage: en ? "Waiting for your review" : "검토를 기다리고 있어요",
      targetStep: 7,
    };
  }
  if (currentUi?.type === "doc_preview") {
    return {
      title: title || (en ? "Document application" : "서류 신청"),
      stage: en ? "Document preview is ready" : "작성된 서류를 확인할 차례예요",
      targetStep: 7,
    };
  }
  if (currentUi?.type === "profile_confirm") {
    return {
      title: en ? "Profile review" : "프로필 확인",
      stage: en ? "Review the information from your documents" : "서류에서 확인한 정보를 검토할 차례예요",
      targetStep: 3,
    };
  }
  if (currentUi?.type === "question" || activeTask) {
    return {
      title: title || (en ? "Document preparation" : "서류 준비"),
      stage: currentUi?.type === "question"
        ? (en ? "Additional information is needed" : "추가 정보를 확인하고 있어요")
        : (en ? "In progress" : "진행 중이에요"),
      targetStep: currentUi?.type === "question" ? 4 : 5,
    };
  }
  return null;
}

function savedProgressDetails(progress, locale = "ko") {
  if (!progress?.memberId) return null;
  const en = locale === "en";
  const targetStep = Number.isInteger(progress.currentStep) ? progress.currentStep : progress.lastStep;
  if (targetStep < 2 || targetStep > 8) return null;
  const completed = Array.isArray(progress.completedScans) ? progress.completedScans : [];
  if (targetStep === 2) {
    const nextPage = SCAN_PAGES.find((page) => !completed.includes(page.key));
    return {
      title: en ? "Document capture" : "서류 촬영",
      stage: nextPage
        ? (en ? `Next: ${nextPage.en[0]}` : `다음: ${nextPage.ko[0]}`)
        : (en ? "All images are ready" : "촬영한 서류를 확인할 차례예요"),
      targetStep: 2,
    };
  }
  const stages = {
    3: ["프로필 확인", "Profile review", "서류에서 확인한 정보를 검토할 차례예요", "Review the information from your documents"],
    4: ["추가 정보 확인", "Additional questions", "필요한 정보를 이어서 확인하고 있어요", "Continue answering the remaining questions"],
    5: ["서류 준비", "Document preparation", "진행 중인 서류 작업을 이어갈 차례예요", "Continue your document task"],
    6: ["심사 결과", "Review result", "확인하던 결과부터 이어갈 수 있어요", "Continue from your saved result"],
    7: ["서류 미리보기", "Document preview", "작성된 서류를 확인할 차례예요", "Review your prepared document"],
    8: ["서류 완료", "Document ready", "완료된 서류를 확인할 수 있어요", "View your completed document"],
  };
  const stage = stages[targetStep];
  return stage ? { title: stage[en ? 1 : 0], stage: stage[en ? 3 : 2], targetStep } : null;
}

const card = {
  padding: 15, borderRadius: 14, border: "1px solid var(--line)", background: "#fff",
};
const H2 = { margin: 0, fontSize: 25, lineHeight: 1.25, fontWeight: 800, letterSpacing: "-0.035em" };
const SUB = { margin: "7px 0 0", fontSize: 14, lineHeight: 1.5, color: "var(--muted)" };
const mono = { fontFamily: "'IBM Plex Mono',monospace" };

export default function App() {
  const [step, setStep] = useState(1);
  const [isAuthenticated, setIsAuthenticated] = useState(() => Boolean(window.localStorage.getItem("settle_access_token")));
  const [memberId, setMemberId] = useState(readMemberId);
  const [authMode, setAuthMode] = useState("login");
  const [auth, setAuth] = useState(() => ({ ...EMPTY_AUTH }));
  const [authMessage, setAuthMessage] = useState("");
  const [authMessageType, setAuthMessageType] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [newAccountEmail, setNewAccountEmail] = useState("");
  const [showGreeting, setShowGreeting] = useState(false);
  const [savedProgress, setSavedProgress] = useState(() => {
    const progress = readOnboardingProgress();
    return progress?.memberId && memberId && progress.memberId !== memberId ? null : progress;
  });
  const [sessionDrafts, setSessionDrafts] = useState(() => readSessionDrafts(memberId));
  const [lang, setLang] = useState(() => savedProgress?.lang || "ko");
  const [exitConfirmOpen, setExitConfirmOpen] = useState(false);
  const [newDocumentConfirmOpen, setNewDocumentConfirmOpen] = useState(false);

  // ── 에이전트 단일 스토어 ──
  // 서버 state 가 진실의 원천이다. 부분 병합하지 않고 통째로 교체한다.
  const [agentState, setAgentState] = useState(null);
  const [ui, setUi] = useState({ type: "none", payload: {} });
  const [messages, setMessages] = useState([]);
  const [toast, setToast] = useState("");
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionRestoreChecked, setSessionRestoreChecked] = useState(false);

  const [scan, setScan] = useState(0);
  const [shots, setShots] = useState({});
  const [completedScans, setCompletedScans] = useState(() => savedProgress?.completedScans || []);
  // 문자열이 아니라 { message, code, details }. code 가 있어야 재촬영으로
  // 풀리는 오류와 그렇지 않은 오류(validation_failed)를 가를 수 있다.
  const [captureError, setCaptureError] = useState(null);
  const [captureLoading, setCaptureLoading] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraStarting, setCameraStarting] = useState(false);
  const [extract, setExtract] = useState(null);
  const [cardProfileFields, setCardProfileFields] = useState([]);
  const [profileDraft, setProfileDraft] = useState(() => readProfileDraft(memberId)?.profileDraft || {});
  const [dirtyFields, setDirtyFields] = useState(() => readProfileDraft(memberId)?.dirtyFields || {});
  const [profileErrors, setProfileErrors] = useState({});
  const [profileSubmitting, setProfileSubmitting] = useState(false);

  const [answers, setAnswers] = useState(() => savedProgress?.answers || { ...EMPTY_ANSWERS });
  const [verdict, setVerdict] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewActionId, setPreviewActionId] = useState("open_bank_account");
  const [previewBlobUrl, setPreviewBlobUrl] = useState("");
  const [pdfPage, setPdfPage] = useState(1);
  const [approval, setApproval] = useState(null);
  const [approvalVisible, setApprovalVisible] = useState(false);
  const [approvalLoading, setApprovalLoading] = useState(false);
  const [approvalError, setApprovalError] = useState("");
  const [ledger, setLedger] = useState([]);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [ledgerError, setLedgerError] = useState("");
  const [cabinetBackStep, setCabinetBackStep] = useState(7);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [chatInput, setChatInput] = useState("");
  const [taskBusy, setTaskBusy] = useState("");
  const [thinkingSteps, setThinkingSteps] = useState([]);
  const [typingText, setTypingText] = useState(null);
  const chatEndRef = useRef(null);
  const chatScrollRef = useRef(null);
  const fileInputRef = useRef(null);
  const nativeCameraInputRef = useRef(null);
  const videoRef = useRef(null);
  const cameraStreamRef = useRef(null);
  const cameraRequestRef = useRef(false);
  const navigationHistoryRef = useRef([]);
  const progressRef = useRef(savedProgress);
  const locale = (agentState?.locale || lang) === "ko" ? "ko" : "en";
  const t = (ko, en) => locale === "en" ? en : ko;
  // 문자열(카메라·브라우저 오류)과 AgentError(서버 계약) 양쪽을 받는다.
  const showCaptureError = (source) => setCaptureError(typeof source === "string"
    ? { message: source, code: "", details: {} }
    : { message: captureMessage(source, locale), code: source?.code || "", details: source?.details || {} });
  const scanPages = SCAN_PAGES.map((page) => ({
    ...page,
    label: page[locale][0],
    sub: page[locale][1],
  }));

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    if (authMessageType !== "success" || !authMessage) return;
    const timeoutId = window.setTimeout(() => {
      setAuthMessage("");
      setAuthMessageType("");
    }, 3000);
    return () => window.clearTimeout(timeoutId);
  }, [authMessage, authMessageType]);

  useEffect(() => {
    if (!showGreeting) return undefined;
    const timeoutId = window.setTimeout(() => setShowGreeting(false), 2000);
    return () => window.clearTimeout(timeoutId);
  }, [showGreeting]);

  const stopCamera = () => {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;
    setCameraOpen(false);
  };

  const startCamera = async (allowNativeFallback = true) => {
    if (cameraRequestRef.current || cameraStreamRef.current) return;
    cameraRequestRef.current = true;
    setCaptureError(null);
    setCameraStarting(true);
    let timeoutId;
    let timedOut = false;
    let streamRequest;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        if (allowNativeFallback) nativeCameraInputRef.current?.click();
        else showCaptureError(t("이 브라우저는 웹 카메라를 지원하지 않아요. 기기 카메라로 열기를 눌러 주세요.", "This browser does not support the web camera. Use the device camera instead."));
        return;
      }
      streamRequest = navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      const timeout = new Promise((_, reject) => {
        timeoutId = window.setTimeout(() => {
          timedOut = true;
          reject(new Error(t("브라우저가 카메라 요청에 응답하지 않았어요. Chrome를 완전히 종료한 뒤 다시 실행해 주세요.", "The browser did not respond to the camera request. Fully close Chrome and try again.")));
        }, 8000);
      });
      cameraStreamRef.current = await Promise.race([streamRequest, timeout]);
      setCameraOpen(true);
    } catch (error) {
      if (timedOut) streamRequest?.then((stream) => stream.getTracks().forEach((track) => track.stop())).catch(() => {});
      showCaptureError(error?.name === "NotAllowedError" ? t("카메라 권한을 허용해 주세요.", "Allow camera access to continue.") : error instanceof Error ? error.message : t("카메라를 열지 못했어요.", "Could not open the camera."));
    } finally {
      window.clearTimeout(timeoutId);
      cameraRequestRef.current = false;
      setCameraStarting(false);
    }
  };

  useEffect(() => {
    if (step !== 4) return;
    const frame = requestAnimationFrame(() => {
      const container = chatScrollRef.current;
      if (container) container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
      chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
    return () => cancelAnimationFrame(frame);
  }, [step, chatLoading, messages, typingText, ui, thinkingSteps]);

  useEffect(() => {
    if (cameraOpen && videoRef.current && cameraStreamRef.current) {
      videoRef.current.srcObject = cameraStreamRef.current;
      videoRef.current.play().catch(() => showCaptureError(t("카메라 미리보기를 시작하지 못했어요.", "Could not start the camera preview.")));
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
      .catch((error) => { if (active) setLedgerError(localizedError(error, locale, "실행 이력을 불러오지 못했어요.", "Could not load the action history.")); })
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
    if (!isAuthenticated || !memberId || step < 1 || step > 9) return;
    const previous = progressRef.current || {};
    const next = {
      ...previous,
      lang,
      uiLanguageVersion: UI_LANGUAGE_VERSION,
      sessionId,
      lastStep: Math.max(previous.lastStep || 1, step),
      currentStep: step,
      completedScans,
      answers,
      memberId,
      updatedAt: new Date().toISOString(),
    };
    progressRef.current = next;
    window.localStorage.setItem(ONBOARDING_PROGRESS_KEY, JSON.stringify(next));
    setSavedProgress(next);
  }, [answers, completedScans, isAuthenticated, lang, memberId, sessionId, step]);

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

  const returnToChat = () => {
    if (approval?.action_id) {
      const title = APPLICATIONS[approval.action_id]?.[locale] || approval.title || t("작성한 서류", "Prepared document");
      const contextMessage = t(
        `${title} 작성이 완료되어 발급 검토를 기다리고 있어요. 아래 카드에서 내용을 확인한 뒤 진행해 주세요.`,
        `${title} is ready for issuance review. Check the details in the card below before continuing.`,
      );
      setMessages((current) => {
        const next = [...current];
        for (let index = next.length - 1; index >= 0; index -= 1) {
          if (next[index].from !== "agent") continue;
          if (/^아래 내용을 실행할까요\?$|^Would you like to execute/i.test(next[index].text?.trim() || "")) {
            next[index] = { ...next[index], text: contextMessage };
          }
          break;
        }
        return next;
      });
    }
    go(4);
  };

  const back = (fallback = 0) => {
    const previousStep = navigationHistoryRef.current.pop();
    setStep(previousStep ?? fallback);
  };

  const backFromConsultation = () => {
    if (cardProfileFields.length > 0) {
      back(3);
      return;
    }
    while ([2, 3, 4].includes(navigationHistoryRef.current.at(-1))) {
      navigationHistoryRef.current.pop();
    }
    const nextScan = SCAN_PAGES.findIndex((page) => !shots[page.key]);
    setScan(nextScan < 0 ? 0 : nextScan);
    setStep(2);
  };

  const requestOnboardingExit = () => setExitConfirmOpen(true);

  // PR #63의 즉시 언어 전환 동작을 유지한다. 서버 상태의 locale도 함께
  // 갱신해야 현재 화면과 다음 API 요청의 언어가 어긋나지 않는다.
  const changeLocale = (next) => {
    if (next !== "ko" && next !== "en") return;
    if (next === locale) return;
    setLang(next);
    setAgentState((current) => (current ? { ...current, locale: next } : current));
  };

  const exitOnboarding = () => {
    stopCamera();
    setExitConfirmOpen(false);
    setNewDocumentConfirmOpen(false);
    navigationHistoryRef.current = [];
    setStep(0);
  };

  const openPdfPreview = async () => {
    if (previewLoading) return;
    setPreviewLoading(true);
    setApprovalVisible(false);
    setPreviewError("");
    try {
      const response = applyAgent(await previewAction(previewActionId, sessionId, locale));
      const responseUi = readUi(response);
      if (responseUi.type === "question") {
        go(4);
        return;
      }
      if (responseUi.type === "approval") {
        return;
      }
      if (responseUi.type !== "doc_preview") {
        throw new Error(response?.reply || t("PDF 미리보기 응답을 확인해 주세요.", "Check the PDF preview response."));
      }
      const payload = responseUi.payload;
      const blob = await fetchDocument(payload.preview_url);
      const nextBlobUrl = URL.createObjectURL(blob);
      setPreviewBlobUrl((current) => {
        if (current) URL.revokeObjectURL(current);
        return nextBlobUrl;
      });
      setPreview(payload);
      setPdfPage(1);
      go(10);
    } catch (error) {
      if (!handleAuthError(error)) setPreviewError(localizedError(error, locale, "PDF를 불러오지 못했어요.", "Could not load the PDF."));
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
      setPdfPage(1);
      go(10);
    } catch (error) {
      if (!handleAuthError(error)) setPreviewError(localizedError(error, locale, "PDF를 불러오지 못했어요.", "Could not load the PDF."));
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
      if (!handleAuthError(error)) setPreviewError(localizedError(error, locale, "PDF를 다운로드하지 못했어요.", "Could not download the PDF."));
    }
  };

  const decideApproval = async (approved) => {
    if (approvalLoading || !approval?.action_id) return;
    setApprovalLoading(true);
    setApprovalError("");
    try {
      const response = applyAgent(await approveAction(approval.action_id, sessionId, approved, locale));
      const nextUi = readUi(response);
      setApprovalVisible(false);
      if (nextUi.type === "question") {
        go(4);
        return;
      }
      if (approved) {
        setCabinetBackStep(7);
        go(9);
      }
    } catch (error) {
      if (!handleAuthError(error)) setApprovalError(localizedError(error, locale, "승인 요청을 처리하지 못했어요.", "Could not process the approval request."));
    } finally {
      setApprovalLoading(false);
    }
  };

  // AgentResponse 처리 순서는 계약대로 setState → render(ui) → appendMessage(reply).
  const applyAgent = (response) => {
    if (response?.state) {
      setAgentState(response.state);
      if (memberId && response.state.session_id) {
        const snapshot = {
          memberId,
          sessionId: response.state.session_id,
          tasks: Array.isArray(response.state.tasks) ? response.state.tasks : [],
          updatedAt: new Date().toISOString(),
        };
        const allDrafts = readSessionDrafts();
        const nextDrafts = [snapshot, ...allDrafts.filter((draft) =>
          !(draft.memberId === memberId && draft.sessionId === snapshot.sessionId))].slice(0, 20);
        window.localStorage.setItem(SESSION_DRAFTS_KEY, JSON.stringify(nextDrafts));
        setSessionDrafts(nextDrafts.filter((draft) => draft.memberId === memberId));
      }
    }
    const responseUi = readUi(response);
    setUi(responseUi);
    const repeatedQuestion = responseUi.type === "question"
      && response?.reply?.trim() === responseUi.payload?.label?.trim();
    if (response?.reply && !repeatedQuestion) {
      setMessages((current) => [...current, { from: "agent", text: response.reply }]);
    }
    const nextApproval = response?.ui?.type === "approval"
      ? response.ui.payload
      : response?.state?.pending_approval;
    setApproval(nextApproval || null);
    return response;
  };

  const resetUserUiState = () => {
    stopCamera();
    clearToken();
    window.localStorage.removeItem(ONBOARDING_PROGRESS_KEY);
    window.sessionStorage.removeItem(PROFILE_DRAFT_KEY);
    if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    progressRef.current = null;
    navigationHistoryRef.current = [];
    setIsAuthenticated(false);
    setMemberId("");
    setSavedProgress(null);
    setLang("ko");
    setExitConfirmOpen(false);
    setAgentState(null);
    setUi({ type: "none", payload: {} });
    setMessages([]);
    setToast("");
    setSessionLoading(false);
    setSessionRestoreChecked(false);
    setScan(0);
    setShots({});
    setCompletedScans([]);
    setCaptureError(null);
    setCaptureLoading(false);
    setCameraStarting(false);
    setExtract(null);
    setCardProfileFields([]);
    setProfileDraft({});
    setDirtyFields({});
    setProfileErrors({});
    setProfileSubmitting(false);
    setAnswers({ ...EMPTY_ANSWERS });
    setVerdict(null);
    setChatLoading(false);
    setChatInput("");
    setPreview(null);
    setPreviewActionId("open_bank_account");
    setPreviewBlobUrl("");
    setPreviewError("");
    setPreviewLoading(false);
    setApproval(null);
    setApprovalVisible(false);
    setApprovalLoading(false);
    setApprovalError("");
    setLedger([]);
    setLedgerLoading(false);
    setLedgerError("");
    setCabinetBackStep(7);
    setTaskBusy("");
    setAuthMode("login");
    setAuth({ ...EMPTY_AUTH });
    setAuthMessage("");
    setAuthMessageType("");
    setAuthLoading(false);
    setNewAccountEmail("");
    setShowGreeting(false);
    setStep(0);
  };

  useEffect(() => {
    if (!isAuthenticated || step !== 0 || sessionRestoreChecked) return;
    let active = true;
    setSessionRestoreChecked(true);
    setSessionLoading(true);
    setToast("");
    createSession(lang, !savedProgress, { sessionId: savedProgress?.sessionId })
      .then((response) => { if (active) applyAgent(response); })
      .catch((error) => {
        if (active && !handleAuthError(error)) {
          setToast(localizedError(error, locale, "진행 내용을 확인하지 못했어요.", "Could not check your progress."));
        }
      })
      .finally(() => { if (active) setSessionLoading(false); });
    return () => { active = false; };
  }, [isAuthenticated, step]);

  // 401/403 이면 세션을 이어갈 방법이 없다. 토큰을 버리고 로그인부터 다시 받는다.
  // 처리했으면 true — 호출부는 자기 화면 오류를 띄우지 않고 빠진다.
  const handleAuthError = (error) => {
    if (error?.status !== 401 && error?.status !== 403) return false;
    resetUserUiState();
    setAuthMessage(localizedError(error, locale, "로그인이 만료됐어요. 다시 로그인해 주세요.", "Your login has expired. Please sign in again."));
    setAuthMessageType("error");
    setStep(-1);
    return true;
  };

  const resumeSession = async (resumeMemberId = memberId) => {
    if (sessionLoading) return;
    setSessionLoading(true);
    setToast("");
    try {
      const response = agentState?.session_id
        ? { state: agentState, ui }
        : applyAgent(await createSession(lang, false, { sessionId: progressRef.current?.sessionId }));
      const restored = extractionFromSession(response);
      const privateDraft = readProfileDraft(resumeMemberId);
      const localProfile = privateDraft?.profileDraft || {};
      const restoredProfile = Object.keys(restored.profile || {}).length > 0 ? restored.profile : localProfile;
      const restoredFields = (restored.fields || []).length > 0
        ? restored.fields
        : Object.entries(localProfile).map(([key, value]) => ({
            key, label: PROFILE_LABELS[key] || key, value, editable: key !== "arc_no",
          }));
      if (restoredFields.length > 0) {
        const serverDraft = Object.fromEntries(
          restoredFields.map((field) => [field.key, field.value ?? restoredProfile[field.key] ?? ""])
        );
        setExtract({ ...restored, profile: restoredProfile, fields: restoredFields });
        setCardProfileFields(restoredFields);
        setProfileDraft({ ...serverDraft, ...(privateDraft?.profileDraft || {}) });
        setDirtyFields(privateDraft?.dirtyFields || {});
        setProfileErrors({});
      }

      const responseUi = readUi(response);
      const hasReusableProfile = REUSABLE_PROFILE_KEYS.every((key) => restoredProfile[key]);
      const allScansCompleted = SCAN_PAGES.every((page) => completedScans.includes(page.key));
      if (hasReusableProfile && completedScans.length === 0) {
        setCompletedScans(SCAN_PAGES.map((page) => page.key));
      }
      const tasks = response?.state?.tasks || [];
      const resumed = resumeDetails(response.state, responseUi, locale)
        || savedProgressDetails(progressRef.current, locale);
      let targetStep = resumed?.targetStep || 2;
      if (!resumed && tasks.length > 0) targetStep = 5;
      else if (!resumed && restoredFields.length > 0 && (allScansCompleted || !hasReusableProfile)) targetStep = 3;
      else if (!resumed && hasReusableProfile) targetStep = 4;
      if (targetStep === 2) {
        const nextScan = SCAN_PAGES.findIndex((page) => !completedScans.includes(page.key));
        setScan(nextScan < 0 ? 0 : nextScan);
      }
      go(targetStep);
    } catch (error) {
      if (!handleAuthError(error)) setToast(localizedError(error, locale, "이전 진행 내용을 불러오지 못했어요.", "Could not restore your previous progress."));
    } finally {
      setSessionLoading(false);
    }
  };

  const startFreshDocumentSession = async () => {
    if (sessionLoading) return;
    setSessionLoading(true);
    setToast("");
    try {
      const response = await createSession(lang, false, {
        fresh: true,
        sourceSessionId: sessionId,
      });
      const nextSessionId = response?.state?.session_id;
      if (!nextSessionId) throw new Error(t("새 상담 세션을 만들지 못했어요.", "Could not create a new consultation session."));

      stopCamera();
      setMessages([]);
      setShots({});
      setCompletedScans([]);
      setScan(0);
      setCaptureError(null);
      setExtract(null);
      setCardProfileFields([]);
      setProfileDraft({});
      setDirtyFields({});
      setProfileErrors({});
      setAnswers({ ...EMPTY_ANSWERS });
      setVerdict(null);
      setPreview(null);
      setPreviewError("");
      setApproval(null);
      setApprovalVisible(false);
      setLedger([]);
      setChatInput("");
      setThinkingSteps([]);
      applyAgent(response);

      const hasMasterProfile = Object.keys(response?.state?.profile || {}).length > 0;
      const targetStep = hasMasterProfile ? 4 : 2;
      const nextProgress = {
        lang,
        uiLanguageVersion: UI_LANGUAGE_VERSION,
        memberId,
        sessionId: nextSessionId,
        currentStep: targetStep,
        lastStep: targetStep,
        completedScans: [],
        answers: { ...EMPTY_ANSWERS },
        updatedAt: new Date().toISOString(),
      };
      progressRef.current = nextProgress;
      window.localStorage.setItem(ONBOARDING_PROGRESS_KEY, JSON.stringify(nextProgress));
      setSavedProgress(nextProgress);
      navigationHistoryRef.current = [];
      setNewDocumentConfirmOpen(false);
      setStep(targetStep);
    } catch (error) {
      if (!handleAuthError(error)) setToast(localizedError(error, locale, "새 상담을 시작하지 못했어요.", "Could not start a new consultation."));
      setNewDocumentConfirmOpen(false);
    } finally {
      setSessionLoading(false);
    }
  };

  const openSavedWork = async (draftSessionId, actionId) => {
    if (sessionLoading) return;
    if (draftSessionId === sessionId) {
      setPreviewActionId(actionId);
      go(7);
      return;
    }
    setSessionLoading(true);
    setToast("");
    try {
      setMessages([]);
      const response = await createSession(lang, false, { sessionId: draftSessionId });
      applyAgent(response);
      setPreviewActionId(actionId);
      const nextProgress = {
        ...(progressRef.current || {}), memberId, lang,
        uiLanguageVersion: UI_LANGUAGE_VERSION,
        sessionId: draftSessionId,
        currentStep: 7,
        lastStep: Math.max(progressRef.current?.lastStep || 1, 7),
        updatedAt: new Date().toISOString(),
      };
      progressRef.current = nextProgress;
      window.localStorage.setItem(ONBOARDING_PROGRESS_KEY, JSON.stringify(nextProgress));
      setSavedProgress(nextProgress);
      navigationHistoryRef.current = [];
      setStep(7);
    } catch (error) {
      if (!handleAuthError(error)) setToast(localizedError(error, locale, "저장된 작업을 열지 못했어요.", "Could not open the saved work."));
    } finally {
      setSessionLoading(false);
    }
  };

  const approvalModal = approval && approvalVisible && step === 10
    ? <ApprovalModal approval={approval} loading={approvalLoading} error={approvalError} onDecision={decideApproval} locale={locale} />
    : null;
  const activeModal = exitConfirmOpen
    ? <ExitConfirmModal onContinue={() => setExitConfirmOpen(false)} onExit={exitOnboarding} locale={locale} />
    : newDocumentConfirmOpen
      ? <NewDocumentConfirmModal
          loading={sessionLoading}
          onContinue={() => setNewDocumentConfirmOpen(false)}
          onStart={startFreshDocumentSession}
          locale={locale}
        />
      : approvalModal;

  const openCabinetFromHome = async () => {
    if (sessionLoading) return;
    setSessionLoading(true);
    setCabinetBackStep(0);
    setToast("");
    try {
      const response = agentState?.session_id ? null : await createSession(lang);
      if (response) applyAgent(response);
      if (!(response?.state?.session_id || agentState?.session_id)) {
        throw new Error(t("상담 세션을 확인하지 못했어요.", "Could not find your consultation session."));
      }
      go(9);
    } catch (error) {
      if (!handleAuthError(error)) setToast(localizedError(error, locale, "서류함을 불러오지 못했어요.", "Could not open your documents."));
    } finally {
      setSessionLoading(false);
    }
  };

  // ── 0 스플래시 ──
  if (step === 0)
    {
      const resumed = resumeDetails(agentState, ui, locale)
        || savedProgressDetails(savedProgress, locale);
      const hasProfile = Object.keys(agentState?.profile || {}).length > 0;
      // PR #63 재방문 홈: 진행 중 / 프로필 보유 / 프로필 없음 세 상태 중 하나만 보인다.
      if (isAuthenticated) {
        const homeState = resumed ? "resume" : hasProfile ? "profile" : "start";
        const progressByStep = { 2: 22, 3: 45, 4: 60, 5: 72, 6: 82, 7: 92, 8: 100 };
        const progressPercent = resumed ? progressByStep[resumed.targetStep] || 22 : 0;
        const savedDate = savedProgress?.updatedAt
          ? new Date(savedProgress.updatedAt).toLocaleDateString(locale === "en" ? "en-CA" : "ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" }).replace(/\. /g, ".").replace(/\.$/, "")
          : "";
        const startNewDocument = () => {
          if (resumed) setNewDocumentConfirmOpen(true);
          else if (hasProfile) startFreshDocumentSession();
          else resumeSession();
        };
        return (
          <Shell modal={activeModal}>
            <div className="splash-lang"><LangToggle locale={locale} onChange={changeLocale} /></div>
            <div className="resume-home">
              <div className="resume-home-center">
                <div className="resume-home-brand">
                  <BridgeMark size={78} />
                  <div className="return-greeting">
                    {homeState === "start" ? t("환영해요", "Welcome") : t("다시 오셨네요", "Welcome back")}
                    <span className={`wave-hello${showGreeting ? " visible" : ""}`} aria-hidden="true">👋</span>
                  </div>
                </div>
                {homeState === "resume" && (
                  <section className="resume-card resume-card--progress" aria-label={t("저장된 진행 상황", "Saved progress")}>
                    <div className="resume-card-kicker">{t("이어서 하기", "Continue")}</div>
                    <h2>{resumed.title}</h2><p>{resumed.stage}</p>
                    {savedDate && <time dateTime={savedProgress.updatedAt}>{t("마지막 저장", "Last saved")} · {savedDate}</time>}
                    <div className="resume-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={progressPercent}><span style={{ width: `${progressPercent}%` }} /></div>
                    <button type="button" disabled={sessionLoading} onClick={resumeSession}>{sessionLoading ? t("불러오는 중…", "Loading…") : t("이어서 하기", "Continue")}</button>
                  </section>
                )}
                {homeState === "start" && (
                  <section className="resume-card resume-card--start" aria-label={t("시작 전", "Not started")}>
                    <div className="resume-card-kicker">{t("시작 전", "Not started")}</div>
                    <h2>{t("먼저 프로필을 만들어요", "Create your profile first")}</h2>
                    <p>{t("외국인등록증을 촬영하면 정보를 자동으로 채워드려요.", "Scan your residence card and we'll fill in your details automatically.")}</p>
                  </section>
                )}
                {homeState === "resume" && <button type="button" className="resume-btn resume-btn-secondary" onClick={startNewDocument}>{t("새 서류 발급하기", "Prepare a new document")}</button>}
                {homeState === "profile" && <>
                  <button type="button" className="resume-btn resume-btn-primary" disabled={sessionLoading} onClick={startNewDocument}>{t("새 서류 발급하기", "Prepare a new document")}</button>
                  <button type="button" className="resume-btn resume-btn-secondary" onClick={openCabinetFromHome}><span aria-hidden="true">🗂️</span> {sessionLoading ? t("서류함 불러오는 중…", "Opening documents…") : t("내 서류함", "My documents")}</button>
                </>}
                {homeState === "start" && <button type="button" className="resume-btn resume-btn-primary" disabled={sessionLoading} onClick={startNewDocument}>{sessionLoading ? t("진행 내용 확인 중…", "Checking your progress…") : t("프로필 만들기", "Create profile")}</button>}
                {toast && <div role="alert" className="capture-error" style={{ margin: 0 }}>{toast}</div>}
              </div>
              <button type="button" onClick={resetUserUiState} className="text-action resume-logout">{t("로그아웃", "Sign out")}</button>
            </div>
          </Shell>
        );
      }
      return (
      <Shell modal={activeModal}>
        <div className="splash-lang"><LangToggle locale={locale} onChange={changeLocale} /></div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 26, padding: "40px 34px" }}>
          <BridgeMark size={104} />
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            {isAuthenticated && <div className="return-greeting">{t("다시 오셨네요", "Welcome back")}<span className={`wave-hello${showGreeting ? " visible" : ""}`} aria-hidden="true">👋</span></div>}
          </div>
          <div style={{ width: 34, height: 1, background: "var(--line)" }} />
          <div style={{ fontSize: 15, lineHeight: 1.55, color: "oklch(0.45 0.012 60)", textAlign: "center", maxWidth: 250 }}>
            {t("은행은 한 번만 가세요.", "Visit the bank only once.")}<br />{t("서류는 저희가 먼저 준비해요.", "We prepare your documents first.")}
          </div>
        </div>
        <div style={{ padding: "0 30px 40px", display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
          <div style={{ padding: "7px 13px", borderRadius: 999, background: "oklch(0.93 0.008 60)", ...mono, fontSize: 11, fontWeight: 700, letterSpacing: "0.1em" }}>
            D-2 STUDENT VISA · BETA
          </div>
          {isAuthenticated && resumed && (
            <div className="saved-progress-note" role="status">
              <span aria-hidden="true">↗</span>
              <div><b>{resumed.title}</b><small>{resumed.stage}</small></div>
            </div>
          )}
          {isAuthenticated && !sessionLoading && !resumed && !hasProfile && (
            <div className="saved-progress-note" role="status">
              <span aria-hidden="true">＋</span>
              <div><b>{t("프로필부터 만들어 볼까요?", "Let's create your profile")}</b><small>{t("서류 사진을 등록하면 필요한 절차를 안내해 드려요.", "Upload your documents to get personalized guidance.")}</small></div>
            </div>
          )}
          <div style={{ width: "100%" }}>
            <PrimaryButton disabled={sessionLoading} onClick={() => {
              if (isAuthenticated && resumed) resumeSession();
              else if (isAuthenticated) resumeSession();
              else {
                setAuthMode("login");
                go(-1);
              }
            }}>{sessionLoading
              ? t("진행 내용 확인 중…", "Checking your progress…")
              : resumed
                ? t("이어서 하기", "Continue")
                : isAuthenticated && hasProfile
                  ? t("새 서류 준비하기", "Prepare a new document")
                  : isAuthenticated
                    ? t("프로필 만들기", "Create profile")
                    : t("로그인", "Sign in")}</PrimaryButton>
          </div>
          {!isAuthenticated && (
            <button type="button" onClick={() => {
              setAuthMode("signup");
              go(-1);
            }} className="text-action">{t("계정이 없나요? 회원가입", "Need an account? Sign up")}</button>
          )}
          {isAuthenticated && resumed && (
            <button type="button" onClick={() => go(1)} className="text-action">{t("언어 설정부터 다시 보기", "Choose language again")}</button>
          )}
          {isAuthenticated && (
            <div onClick={openCabinetFromHome} className="tap" style={{ width: "100%", minHeight: 50, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 14, border: "1px solid oklch(0.85 0.01 60)", background: "#fff", fontSize: 14, fontWeight: 700 }}>
              <span aria-hidden="true">🗂️</span> {sessionLoading ? t("서류함 불러오는 중…", "Opening documents…") : t("내 서류함 열기", "Open my documents")}
            </div>
          )}
          {isAuthenticated && (
            <button type="button" onClick={resetUserUiState} className="text-action">{t("로그아웃", "Sign out")}</button>
          )}
          {toast && <div role="alert" className="capture-error" style={{ margin: 0 }}>{toast}</div>}
        </div>
      </Shell>
      );
    }

  // ── 인증 ──
  if (step === -1) {
    const signup = authMode === "signup";
    const normalizedEmail = auth.email.trim();
    const validEmail = normalizedEmail.length <= 254 && EMAIL_PATTERN.test(normalizedEmail);
    const rules = passwordChecks(auth.password, locale);
    const validPassword = rules.every((rule) => rule.met) && /^[\x21-\x7E]+$/.test(auth.password);
    const passwordMatches = Boolean(auth.passwordConfirm) && auth.password === auth.passwordConfirm;
    const passwordEligible = validPassword;
    const canSubmit = validEmail && passwordEligible && (signup ? passwordMatches : true);
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
          setNewAccountEmail(normalizedEmail.toLowerCase());
          setAuthMode("login");
          setAuth({ ...EMPTY_AUTH });
          setAuthMessage(t("회원가입이 완료됐어요. 새 계정으로 로그인해 주세요.", "Your account is ready. Sign in with your new account."));
          setAuthMessageType("success");
          return;
        }
        const firstLoginAfterSignup = newAccountEmail === normalizedEmail.toLowerCase();
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
        try {
          applyAgent(await createSession(lang));
        } catch (sessionError) {
          if (handleAuthError(sessionError)) return;
          setAgentState(null);
          setUi({ type: "none", payload: {} });
          setToast(localizedError(sessionError, locale, "진행 내용을 확인하지 못했어요.", "Could not check your progress."));
        }
        setSessionRestoreChecked(true);
        navigationHistoryRef.current = [];
        setNewAccountEmail("");
        if (firstLoginAfterSignup) {
          setShowGreeting(false);
          setStep(2);
        } else {
          setShowGreeting(true);
          setStep(0);
        }
      } catch (error) {
        setAuthMessage(authErrorMessage(error, locale));
        setAuthMessageType("error");
      } finally {
        setAuthLoading(false);
      }
    };
    return (
      <Shell modal={activeModal}>
        <TopBar title={signup ? t("회원가입", "Sign up") : t("로그인", "Sign in")} onBack={() => back(0)} right={<LangToggle locale={locale} onChange={changeLocale} />} />
        <div style={{ padding: "18px 26px 12px" }}>
          <BridgeMark size={56} />
          <h2 style={{ ...H2, marginTop: 20 }}>{signup ? t("MAITE를 시작해요", "Create your MAITE profile") : t("다시 만나서 반가워요", "Nice to see you again")}</h2>
          <p style={SUB}>{signup ? t("사용할 이메일과 안전한 비밀번호를 입력해 주세요.", "Enter your email and a secure password.") : t("이메일과 비밀번호를 입력해 주세요.", "Enter your email and password.")}</p>
        </div>
        <form onSubmit={submitAuth} className="scroll" style={{ padding: "12px 26px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
          {authMessageType === "error" && authMessage && <div role="alert" className="auth-notice error">{authMessage}</div>}
          <AuthInput label={t("이메일", "Email")} type="email" value={auth.email} onChange={updateAuth("email")} placeholder="name@example.com" autoComplete="email" autoCapitalize="none" spellCheck={false} maxLength={254} aria-invalid={Boolean(auth.email) && !validEmail} valid={validEmail} />
          {auth.email && !validEmail && <FieldHint tone="error">{t("영문 이메일 형식으로 입력해 주세요. (예: name@example.com)", "Enter a valid email address, such as name@example.com.")}</FieldHint>}
          {validEmail && <div className="auth-inline-hint">✓ {t("@ 포함 이메일 형식", "Valid email format")}</div>}
          <AuthInput label={t("비밀번호", "Password")} type="password" value={auth.password} onChange={updateAuth("password")} placeholder={t("비밀번호를 입력하세요", "Enter your password")} autoComplete={signup ? "new-password" : "current-password"} maxLength={64} aria-invalid={Boolean(auth.password) && !passwordEligible} valid={Boolean(auth.password) && passwordEligible} />
          {!signup && authMessageType === "success" && authMessage && <div role="status" className="auth-notice success">{authMessage}</div>}
          <div className="password-guide login" aria-label={t("비밀번호 조건", "Password requirements")} aria-live="polite">
            <div>{rules.map((rule) => <span key={rule.label} className={auth.password && rule.met ? "met" : ""}>{auth.password && rule.met ? "✓" : "○"} {rule.label}</span>)}</div>
          </div>
          {signup && (
            <>
              <AuthInput label={t("비밀번호 확인", "Confirm password")} type="password" value={auth.passwordConfirm} onChange={updateAuth("passwordConfirm")} placeholder={t("비밀번호를 다시 입력하세요", "Enter your password again")} autoComplete="new-password" maxLength={64} aria-invalid={Boolean(auth.passwordConfirm) && !passwordMatches} valid={passwordMatches} indicator={t("일치", "Match")} />
              {auth.passwordConfirm && !passwordMatches && <FieldHint tone="error">{t("입력한 비밀번호가 서로 일치하지 않아요.", "The passwords do not match.")}</FieldHint>}
              <div className="visa-choice-group" role="group" aria-label={t("체류자격", "Visa status")}>
                <b>{t("체류자격(비자)", "Visa status")}</b>
                <button type="button" className="visa-choice selected" aria-pressed="true">
                  <span>{t("D-2 유학", "D-2 Student")}</span><span aria-hidden="true">✓</span>
                </button>
                <button type="button" className="visa-choice" disabled>
                  <span>{t("D-4 연수", "D-4 Training")}</span><span aria-hidden="true">🔒</span>
                </button>
                <button type="button" className="visa-choice" disabled>
                  <span>{t("D-10 구직", "D-10 Job seeking")}</span><span aria-hidden="true">🔒</span>
                </button>
                <button type="button" className="visa-choice" disabled>
                  <span>{t("기타", "Other")}</span><span aria-hidden="true">🔒</span>
                </button>
              </div>
            </>
          )}
        </form>
        <div className="bottom-cta" style={{ paddingTop: 12, paddingLeft: 26, paddingRight: 26 }}>
          <PrimaryButton disabled={!canSubmit || authLoading} onClick={() => submitAuth({ preventDefault() {} })}>{authLoading ? t("처리 중…", "Processing…") : signup ? t("회원가입", "Sign up") : t("로그인", "Sign in")}</PrimaryButton>
          <button type="button" onClick={switchAuthMode}
            style={{ width: "100%", minHeight: 46, marginTop: 8, border: 0, background: "transparent", color: "var(--muted)", fontSize: 13 }}>
            {signup ? t("이미 계정이 있나요? 로그인", "Already have an account? Sign in") : t("계정이 없나요? 회원가입", "Need an account? Sign up")}
          </button>
        </div>
      </Shell>
    );
  }

  // ── 1 언어 선택 ──
  if (step === 1) {
    return (
      <Shell modal={activeModal}>
        {isAuthenticated && <TopBar title={t("설정", "Settings")} onBack={() => back(0)} right={<ExitButton locale={locale} onClick={() => go(0)} />} />}
        <div className="scroll" style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center", gap: 28, padding: "0 26px" }}>
          <div>
            <h2 style={H2}>{t("사용할 언어를 선택하세요", "Choose your language")}</h2>
            <p style={SUB}>{t("앱을 열면 가장 먼저 나와요. 나중에 바꿀 수 있어요.", "It's the first thing you see when you open the app. You can change it later.")}</p>
          </div>
          <div className="language-list">
            <LanguageChoice title="한국어" subtitle="Korean" selected={lang === "ko"} onClick={() => changeLocale("ko")} />
            <LanguageChoice title="English" subtitle="영어" selected={lang === "en"} onClick={() => changeLocale("en")} />
          </div>
        </div>
        <div className="bottom-cta" style={{ paddingTop: 8, paddingLeft: 26, paddingRight: 26 }}>
          {toast && <div role="alert" className="capture-error" style={{ margin: "0 0 10px" }}>{toast}</div>}
          <PrimaryButton disabled={sessionLoading} onClick={() => go(0)}>
            {t("계속", "Continue")}
          </PrimaryButton>
        </div>
      </Shell>
    );
  }

  // ── 2 촬영 ──
  if (step === 2) {
    const uploadPng = async (png) => {
      setCaptureError(null);
      setCaptureLoading(true);
      try {
        const page = scanPages[scan];
        const data = await uploadAndExtract(png, page.docType, sessionId, locale);
        const next = { ...shots, [page.key]: png };
        const nextCompletedScans = [...new Set([...completedScans, page.key])];
        setShots(next);
        setCompletedScans(nextCompletedScans);
        const incomingFields = data.fields || [];
        const isCardDocument = page.docType === "arc_front" || page.docType === "arc_back";
        const mergedCardFields = isCardDocument
          ? [...new Map([...cardProfileFields, ...incomingFields].map((field) => [field.key, field])).values()]
          : cardProfileFields;
        if (isCardDocument) setCardProfileFields(mergedCardFields);
        setExtract({ ...data, fields: mergedCardFields });
        if (data.agentResponse) applyAgent(data.agentResponse);
        if (isCardDocument) {
          setProfileDraft((current) => ({
            ...current,
            ...Object.fromEntries(incomingFields.map((field) => [field.key, field.value])),
          }));
        }
        setDirtyFields({});
        setProfileErrors({});
        const empty = scanPages.findIndex((candidate) => !next[candidate.key]);
        if (empty === -1 && nextCompletedScans.length === SCAN_PAGES.length) go(mergedCardFields.length > 0 ? 3 : 4);
        else setScan(empty);
      } catch (error) {
        if (!handleAuthError(error)) showCaptureError(error);
      } finally {
        setCaptureLoading(false);
      }
    };
    const selectImage = async (event) => {
      const source = event.target.files?.[0];
      event.target.value = "";
      if (!source) return;
      setCaptureLoading(true);
      try {
        await uploadPng(await convertImageToPng(source));
      } catch (error) {
        showCaptureError(error);
      } finally {
        setCaptureLoading(false);
      }
    };
    const takePhoto = async () => {
      try {
        const png = await captureVideoFrameAsPng(videoRef.current, `${scanPages[scan].key}.png`);
        stopCamera();
        await uploadPng(png);
      } catch (error) {
        showCaptureError(error);
      }
    };
    const attachFile = () => {
      stopCamera();
      fileInputRef.current?.click();
    };
    const skipCurrentDocument = () => {
      if (captureLoading || cameraStarting) return;
      stopCamera();
      setCaptureError(null);
      setScan((scan + 1) % scanPages.length);
    };
    const currentShot = shots[scanPages[scan].key];
    const captureActivated = cameraStarting || captureLoading || cameraOpen || Boolean(currentShot);
    return (
      <Shell modal={activeModal}>
        <TopBar title={t("서류 촬영", "Capture documents")} onBack={() => back(1)} right={<TopActions locale={locale} onLocale={changeLocale} onExit={requestOnboardingExit} />} />
        <Rail active={1} locale={locale} />
        <div style={{ padding: "4px 24px 12px" }}>
          <h2 style={H2}>{t("3장을 촬영하세요", "Capture 3 images")}</h2>
        </div>
        <div className="capture-tabs">
          {scanPages.map((p, i) => {
            const done = shots[p.key], active = scan === i;
            const tabTitle = i === 2 ? t("여권", "Passport") : t("외국인등록증", "Residence card");
            const tabSub = i === 2 ? t("사진면", "Photo page") : p.sub;
            return (
              <div key={p.key} onClick={() => setScan(i)} className={`capture-tab tap${done ? " done" : ""}${active ? " active" : ""}`}
                role="button" tabIndex={0} aria-current={active ? "step" : undefined}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setScan(i); }}>
                <span className="capture-tab-title">{done ? "✓ " : ""}{tabTitle}</span>
                <span className="capture-tab-sub">{tabSub}</span>
              </div>
            );
          })}
        </div>
        <div style={{ margin: "0 24px", flex: 1, minHeight: 220, borderRadius: 18, background: "oklch(0.18 0.012 60)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 8, padding: 20 }}>
          {currentShot && (
            <div style={{ width: 40, height: 40, borderRadius: 99, background: "var(--ok)", color: "#fff", fontSize: 20, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>✓</div>
          )}
          {captureActivated
            ? <div className={`scan-preview${captureLoading ? " loading" : ""}`}>
            {captureLoading
              ? <CaptureProgress locale={locale} />
              : cameraOpen
              ? <video ref={videoRef} autoPlay playsInline muted aria-label={`${scanPages[scan].label} ${t("카메라 미리보기", "camera preview")}`} />
              : currentShot
              ? <ImagePreview file={currentShot} alt={`${scanPages[scan].label} ${t("촬영 미리보기", "preview")}`} />
              : <div style={{ ...mono, fontSize: 11, color: "oklch(0.7 0.01 60)", textAlign: "center" }}>{scanPages[scan].label}</div>}
          </div>
            : <div className="scan-preview scan-idle" aria-label={t("촬영 또는 파일 첨부 대기", "Waiting for camera or file upload")}>
                <span className="scan-idle-label">{scanPages[scan].label}</span>
              </div>}
          <div style={{ alignSelf: "stretch", ...mono, fontSize: 10.5, color: "var(--ok)" }}>●&nbsp; {captureLoading ? t("AI가 문서를 읽는 중", "AI is reading the document") : cameraStarting ? t("카메라 준비 중", "Preparing camera") : cameraOpen ? t("카메라 준비됨", "Camera ready") : currentShot ? t("업로드 완료", "Upload complete") : t("촬영하기 또는 파일 첨부를 선택해 주세요", "Choose Camera or File upload")}</div>
        </div>
        <CaptureAlert error={captureError} locale={locale}
          onDeviceCamera={() => nativeCameraInputRef.current?.click()}
          onReviewEarlier={() => {
            setScan(0);
            setCaptureError(null);
            window.setTimeout(() => fileInputRef.current?.click(), 0);
          }} />
        <div className="bottom-cta" style={{ paddingTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
          <input ref={fileInputRef} type="file" accept="image/*" onChange={selectImage} hidden />
          <input ref={nativeCameraInputRef} type="file" accept="image/*" capture="environment" onChange={selectImage} hidden />
          <div style={{ flex: 1 }}><PrimaryButton disabled={captureLoading || cameraStarting} onClick={cameraOpen ? takePhoto : () => startCamera(true)}>{captureLoading ? t("인식 중…", "Reading…") : cameraStarting ? t("연결 중…", "Connecting…") : cameraOpen ? t("사진 찍기", "Take photo") : currentShot ? t("다시 찍기", "Retake") : t("촬영하기", "Camera")}</PrimaryButton></div>
          <button type="button" title={t("파일 첨부", "File upload")} aria-label={t("파일 첨부", "File upload")} disabled={captureLoading || cameraStarting} onClick={attachFile} className="file-attach compact tap">
            {t("파일 첨부", "File upload")}
          </button>
          <button type="button" disabled={captureLoading || cameraStarting} onClick={skipCurrentDocument} className="file-attach compact tap">
            {t("건너뛰기", "Skip")}
          </button>
        </div>
      </Shell>
    );
  }

  // ── 3 프로필 만들기 (OCR 확인) ──
  if (step === 3) {
    const fields = cardProfileFields;
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
        const response = await confirmProfile(sessionId || extract?.state?.session_id, dirtyFields, locale);
        applyAgent(response);
        setExtract((current) => ({
          ...current,
          profile: response.state?.profile || {},
          state: response.state || {},
          agentResponse: response,
        }));
        setDirtyFields({});
        // 프로필 확인만으로 특정 신청을 시작하지 않는다.
        go(4);
      } catch (error) {
        if (handleAuthError(error)) return;
        if (error?.status === 422 && error?.code === "validation_failed") {
          const details = error.details;
          const entries = Array.isArray(details)
            ? details.map((detail) => [detail.field, localizedText(detail.reason || error.message, locale, t("입력값을 확인해 주세요.", "Check this value."))])
            : Object.entries(details || {}).map(([field, reason]) => [field, String(reason)]);
          setProfileErrors(Object.fromEntries(entries.filter(([field]) => field && field !== "message")));
        }
        if (!error?.details || Object.keys(error.details).length === 0) {
          setProfileErrors({ _form: localizedError(error, locale, "프로필을 확인하지 못했어요.", "Could not confirm the profile.") });
        }
      } finally {
        setProfileSubmitting(false);
      }
    };
    return (
      <Shell modal={activeModal}>
        <TopBar title={t("프로필 만들기", "Create profile")} onBack={() => back(2)} right={<TopActions locale={locale} onLocale={changeLocale} onExit={requestOnboardingExit} />} />
        <Rail active={2} locale={locale} />
        <div style={{ padding: "4px 24px 14px" }}>
          <h2 style={H2}>{t("카드에서 만든 프로필", "Profile from your documents")}</h2>
          <p style={SUB}>{t("노란색 항목을 확인하고, 잘못 읽은 값만 수정해 주세요.", "Check highlighted fields and edit only incorrect values.")}</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 9 }}>
          <Label>{t("OCR 추출 결과", "OCR results")}</Label>
          {fields.map((field) => (
            <Field key={field.key} label={profileFieldLabel(field, locale)} value={profileDraft[field.key] ?? field.value}
              confidence={field.confidence} editable={field.editable} dirty={field.key in dirtyFields}
              error={profileErrors[field.key]} onChange={(value) => updateField(field, value)} locale={locale} />
          ))}
          {profileErrors._form && <div role="alert" className="capture-error" style={{ margin: 0 }}>{profileErrors._form}</div>}
        </div>
        <div className="bottom-cta" style={{ paddingTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45 }}>{t("수정 불가 항목은 마스킹된 값으로 전송되지 않아요.", "Read-only masked values are not submitted.")}</div>
          <PrimaryButton disabled={profileSubmitting || fields.length === 0} onClick={submitProfile}>
            {profileSubmitting ? t("확인 중…", "Checking…") : t("확인하고 계속", "Confirm and continue")}
          </PrimaryButton>
        </div>
      </Shell>
    );
  }

  // ── 4 AI 상담 (서버가 내려주는 question 을 그린다) ──
  if (step === 4) {
    if (verdict) {
      const editAnswers = () => setVerdict(null);
      return (
        <Shell modal={activeModal}>
          <TopBar title={t("AI 상담", "AI consultation")} onBack={editAnswers} right={<span className="review-status"><i />{t("심사 완료", "Review complete")}</span>} />
          <Rail active={3} locale={locale} />
          <div className="scroll review-scroll">
            <section className="review-hero">
              <div className="review-kicker">{t("계좌 개설 진단 결과", "ACCOUNT OPENING REVIEW")}</div>
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
              <AccountCard title={t("한도제한계좌", "Limited account")} subtitle={t("한도제한계좌 · 1일 이체 100만원 한도", "Limited account · KRW 1,000,000 daily transfer limit")} account={verdict.limited} />
              <AccountCard title={t("일반계좌", "Standard account")} subtitle={t("일반계좌", "Standard account")} account={verdict.regular} />

              <details className="review-sources">
                <summary>{t("판정 근거", "Review basis")}</summary>
                {verdict.sources.map((source) => <div key={source}>· {source}</div>)}
              </details>
              <p className="review-disclaimer">{t("이 판정은 은행 정책 기준의 사전 점검입니다. 최종 계좌 개설 여부는 은행이 결정합니다.", "This is a preliminary review based on bank policy. The bank makes the final account-opening decision.")}</p>
            </div>
          </div>
          <div className="review-actions">
            <button type="button" onClick={editAnswers} className="review-edit tap">{t("답변 수정", "Edit answers")}</button>
            <button type="button" onClick={() => go(6)} className="review-next tap">{verdictCta(verdict.kind, locale)}</button>
          </div>
        </Shell>
      );
    }

    const question = ui.type === "question" ? ui.payload : null;
    const actionOffer = ui.type === "action_offer" ? ui.payload : null;
    const options = question ? questionOptions(question) : [];

    const openOfferedAction = async () => {
      if (chatLoading || !actionOffer?.action_id) return;
      if (actionOffer.form) {
        setPreviewActionId(actionOffer.action_id);
        go(7);
        return;
      }
      setChatLoading(true);
      setToast("");
      try {
        const response = applyAgent(await startAction(sessionId, actionOffer.action_id, locale));
        const nextUi = readUi(response);
        if (nextUi.type === "document_route") {
          setPreviewActionId(nextUi.payload?.action_id || actionOffer.action_id);
          go(7);
        } else if (nextUi.type === "doc_preview" || nextUi.type === "approval" || nextUi.type === "task_complete") {
          setPreviewActionId(actionOffer.action_id);
          go(nextUi.type === "task_complete" ? 5 : 7);
        }
      } catch (error) {
        if (!handleAuthError(error)) {
          const message = localizedError(error, locale, "기능을 열지 못했어요.", "Could not open this feature.");
          setToast("");
          setUi({ type: "none", payload: {} });
          setMessages((current) => [...current, { from: "agent", text: message }]);
        }
      } finally {
        setChatLoading(false);
      }
    };

    const reopenPendingApproval = async () => {
      if (chatLoading || !approval?.action_id) return;
      setPreviewActionId(approval.action_id);
      setApprovalVisible(false);
      if (!approval.document_id || !approval.preview_url) {
        go(7);
        return;
      }
      setChatLoading(true);
      setToast("");
      try {
        const blob = await fetchDocument(approval.preview_url);
        const nextBlobUrl = URL.createObjectURL(blob);
        setPreviewBlobUrl((current) => {
          if (current) URL.revokeObjectURL(current);
          return nextBlobUrl;
        });
        setPreview({
          document_id: approval.document_id,
          title: approval.doc_title || approval.title,
          preview_url: approval.preview_url,
          pdf_url: approval.pdf_url,
          warnings: approval.warnings || [],
        });
        setPdfPage(1);
        go(10);
      } catch (error) {
        if (!handleAuthError(error)) setToast(localizedError(error, locale, "작성한 서류를 불러오지 못했어요.", "Could not load the prepared document."));
      } finally {
        setChatLoading(false);
      }
    };

    const answer = async (value, displayOverride = "") => {
      if (chatLoading || !value) return;
      const displayValue = displayOverride || options.find((option) => option.value === value)?.label || value;
      setChatLoading(true);
      setToast("");
      setTypingText(null);
      // The submitted card belongs to the previous turn. Remove it before the
      // user's answer is appended so it cannot appear below that answer while
      // the next streamed response is still in flight.
      setUi({ type: "none", payload: {} });
      setMessages((current) => [
        ...current,
        ...(question?.label ? [{ from: "agent", text: question.label }] : []),
        { from: "user", text: displayValue },
      ]);
      setChatInput("");

      setThinkingSteps([]);

      try {
        let response = await sendChatStream(sessionId, value, (label) => {
          setThinkingSteps((current) => current.at(-1) === label ? current : [...current, label]);
        }, locale);
        if (readUi(response).type === "doc_preview") {
          const actionId = response?.state?.pending_approval?.action_id;
          if (actionId) response = await previewAction(actionId, sessionId, locale);
        }
        applyAgent(response);
        if (question?.field === "phone_kr" && response?.state?.profile?.phone_kr) {
          setAnswers((current) => ({ ...current, phone: "yes" }));
        }
        setThinkingSteps([]);

        const reply = response?.reply || "";
        if (reply) {
          setTypingText("");
          let charIdx = 0;
          const typeTimer = setInterval(() => {
            charIdx++;
            if (charIdx <= reply.length) {
              setTypingText(reply.slice(0, charIdx));
            } else {
              clearInterval(typeTimer);
              setTypingText(null);
            }
          }, 30);
        }

        const nextUi = readUi(response);
        if (nextUi.type === "document_route" && nextUi.payload?.action_id) {
          setPreviewActionId(nextUi.payload.action_id);
          setUi({
            type: "action_offer",
            payload: {
              action_id: nextUi.payload.action_id,
              label: APPLICATIONS[nextUi.payload.action_id]?.[locale]
                || t("신청서 작성하기", "Create application"),
            },
          });
        } else if (nextUi.type !== "question" && nextUi.type !== "none" && nextUi.type !== "action_offer") {
          go(5);
        }
      } catch (error) {
        setThinkingSteps([]);
        if (!handleAuthError(error)) setToast(localizedError(error, locale, "메시지를 보내지 못했어요.", "Could not send the message."));
      } finally {
        setChatLoading(false);
      }
    };

    return (
      <Shell modal={activeModal}>
        <TopBar title={t("AI 상담", "AI consultation")} onBack={backFromConsultation} right={<span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--ok)", fontSize: 11.5 }}><span style={{ width: 7, height: 7, borderRadius: 99, background: "var(--ok)" }} />{t("상담 중", "In session")}</span>} />
        <Rail active={3} locale={locale} />
        <div ref={chatScrollRef} className="scroll chat-scroll consultation-chat" style={{ padding: "6px 18px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          {messages.length === 0 && (
            <ChatBubble avatar>
              <strong>{t("\uc548\ub155\ud558\uc138\uc694! AI \uc0c1\ub2f4\uc774\uc5d0\uc694 \ud83d\ude4c", "Hello! I am your AI assistant \ud83d\ude4c")}</strong>
              <span>{t("\ubb34\uc5c7\uc774 \uad81\uae08\ud55c\uc9c0 \ud3b8\ud558\uac8c \ub9d0\uc500\ud574 \uc8fc\uc138\uc694. \uc798 \ubaa8\ub974\uaca0\uc73c\uba74 \u2018\uba54\ub274 \ubcf4\uc5ec\uc918\u2019\ub77c\uace0 \ud558\uc154\ub3c4 \ub3fc\uc694.", "Ask anything. If you are unsure where to start, say 'Show me the menu.'")}</span>
            </ChatBubble>
          )}
          {messages.map((message, index) => {
            const isLastAgent = message.from === "agent" && (index === messages.length - 1 || messages.slice(index + 1).every((m) => m.from === "user"));
            const hasInlineOffer = isLastAgent && actionOffer?.action_id;
            const displayText = isLastAgent && typingText !== null ? typingText : message.text;
            const lines = displayText ? displayText.split("\n") : [];
            return (
              <ChatBubble key={`${message.from}-${index}`} mine={message.from === "user"} avatar={message.from === "agent"}
                compact={message.from === "user" && /^[0-9-]+$/.test(message.text?.trim() || "")}>
                {message.from === "agent" && index === 0 && lines[0] && <strong>{lines[0]}</strong>}
                {lines.slice(message.from === "agent" && index === 0 ? 1 : 0).map((line, li) => (
                  /^(\uadfc\uac70|Sources?)\s*\u00b7/i.test(line)
                    ? <CitationList key={li} line={line} locale={locale} />
                    : <span key={li}>{line || "\u00a0"}</span>
                ))}
                {hasInlineOffer && (
                  <div className="chat-action-offer inline">
                    <span>{actionOffer.presentation === "chat_choice" ? t("어떻게 할까요?", "What would you like to do?") : t("앱에서 바로 진행할 수 있어요", "Available in the app")}</span>
                    {actionOffer.presentation === "chat_choice" ? <div className="chat-choice-actions">
                      <button type="button" disabled={chatLoading} onClick={openOfferedAction}>
                        {actionOffer.primary_label || t("진행하기", "Continue")} <b aria-hidden="true">→</b>
                      </button>
                      <button type="button" className="secondary" disabled={chatLoading}
                        onClick={() => answer(t("아니요", "No"), actionOffer.secondary_label || t("대화하기", "Keep chatting"))}>
                        {actionOffer.secondary_label || t("대화하기", "Keep chatting")}
                      </button>
                    </div> : <button type="button" disabled={chatLoading} onClick={openOfferedAction}>
                      {actionOffer.label || t("기능 열기", "Open feature")} <b aria-hidden="true">→</b>
                    </button>}
                  </div>
                )}
              </ChatBubble>
            );
          })}

          {question && (
            <ChatBubble avatar wide>
              <QuestionCard payload={question} options={options} value={chatInput}
                onChange={setChatInput} onSubmit={answer} disabled={chatLoading} locale={locale} />
            </ChatBubble>
          )}

          {actionOffer?.action_id && !messages.some((message) => message.from === "agent") && (
            <div className="chat-action-offer">
              <span>{t("앱에서 바로 진행할 수 있어요", "Available in the app")}</span>
              <button type="button" disabled={chatLoading} onClick={openOfferedAction}>
                {actionOffer.label || t("기능 열기", "Open feature")} <b aria-hidden="true">→</b>
              </button>
            </div>
          )}

          {approval?.action_id && !actionOffer?.action_id && (
            <div className="chat-action-offer chat-approval-offer">
              <span>{t("발급 검토 대기 중", "Waiting for issuance review")}</span>
              <strong>{APPLICATIONS[approval.action_id]?.[locale] || approval.title}</strong>
              {Array.isArray(approval.summary) && approval.summary.length > 1 && (
                <ul>
                  {approval.summary.slice(1).map((line) => <li key={line}>{line}</li>)}
                </ul>
              )}
              <button type="button" disabled={chatLoading} onClick={reopenPendingApproval}>
                {t("작성 내용 확인하기", "Review prepared document")} <b aria-hidden="true">→</b>
              </button>
            </div>
          )}

          {chatLoading && thinkingSteps.length > 0 && (
            <ChatBubble avatar>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {thinkingSteps.map((label, ti) => (
                  <div key={ti} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: ti === thinkingSteps.length - 1 ? "var(--brand-2)" : "var(--muted)" }}>
                    {ti === thinkingSteps.length - 1 ? <span className="thinking-dot" /> : <span style={{ color: "var(--ok)" }}>✓</span>}
                    {label}
                  </div>
                ))}
              </div>
            </ChatBubble>
          )}

          {toast && <div role="alert" className="capture-error" style={{ margin: 0 }}>{toast}</div>}

          <div ref={chatEndRef} aria-hidden="true" />
        </div>
        <ChatInputBar
          value={chatInput}
          onChange={setChatInput}
          disabled={chatLoading}
          onSend={() => answer(chatInput)}
          locale={locale}
        />
      </Shell>
    );
  }

  // ── 5 할 일 / 과제 선택 ──
  if (step === 5) {
    const tasks = agentState?.tasks || [];
    return <DocumentTaskFlow tasks={tasks} answers={answers} locale={locale}
      modal={activeModal} onBack={() => back(4)} onReturnToChat={returnToChat} onOpen={(actionId) => { setPreviewActionId(actionId); go(7); }} />;

    /* Legacy task list retained below until the next layout cleanup. */
    const startTask = async (task) => {
      if (taskBusy) return;
      setTaskBusy(task.id);
      setToast("");
      if (APPLICATIONS[task.id]) setPreviewActionId(task.id);
      try {
        const response = applyAgent(await startAction(sessionId, task.id, locale));
        // 다음 질문이 오면 상담 화면으로 되돌아간다. 그 밖의 ui 는 담당 파트(6~9)가 그린다.
        if (readUi(response).type === "question") go(4);
      } catch (error) {
        // 409 prerequisite_missing 은 상태를 바꾸지 않고 토스트만 띄운다.
        if (!handleAuthError(error)) setToast(localizedError(error, locale, "과제를 시작하지 못했어요.", "Could not start the task."));
      } finally {
        setTaskBusy("");
      }
    };
    return (
      <Shell modal={activeModal}>
        <TopBar title={t("할 일", "Tasks")} onBack={() => back(4)} />
        <Rail active={3} locale={locale} />
        <div style={{ padding: "4px 24px 14px" }}>
          <h2 style={H2}>{t("지금 할 수 있는 일", "What you can do now")}</h2>
          <p style={SUB}>{t("잠긴 항목은 먼저 끝내야 하는 과제가 있어요.", "Locked tasks require another task to be completed first.")}</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
          {ui.type === "doc_preview" && ui.payload?.document_id && (
            <div style={{ ...card, display: "flex", gap: 13, borderColor: "var(--brand-2)" }}>
              <div style={{ width: 52, height: 70, flex: "none", borderRadius: 7, border: "1px solid oklch(0.88 0.01 60)", background: "repeating-linear-gradient(0deg, oklch(0.9 0.01 60) 0 3px, oklch(0.97 0.008 60) 3px 9px)" }} />
              <div style={{ flex: 1 }}>
                <div style={{ ...mono, fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--brand-2)" }}>{t("방금 만든 신청서", "New application")}</div>
                <b style={{ display: "block", marginTop: 4, fontSize: 14.5 }}>{ui.payload.title}</b>
                <button type="button" onClick={() => openStoredDocument(ui.payload)} className="tap"
                  style={{ marginTop: 8, padding: 0, border: 0, background: "transparent", color: "var(--brand-2)", fontSize: 11.5, fontWeight: 700 }}>
                  {t("미리보기", "Preview")}
                </button>
              </div>
            </div>
          )}
          {ui.type === "task_complete" && (
            <div role="status" style={{ ...card, padding: 15, borderColor: "var(--ok)", background: "oklch(0.97 0.025 145)" }}>
              <div style={{ ...mono, fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--ok)" }}>
                {t("\uc644\ub8cc", "Completed")}
              </div>
              <b style={{ display: "block", marginTop: 5, fontSize: 14.5 }}>
                {ui.payload?.title || t("\ud560 \uc77c\uc744 \uc644\ub8cc\ud588\uc5b4\uc694.", "The task is complete.")}
              </b>
              {ui.payload?.phone_kr && (
                <div style={{ marginTop: 6, fontSize: 12, color: "var(--muted)" }}>
                  {t("\uad6d\ub0b4 \uc804\ud654\ubc88\ud638", "Mobile number")} · {ui.payload.phone_kr}
                </div>
              )}
            </div>
          )}
          {tasks.length === 0 && (
            <div style={{ ...card, fontSize: 12.5, color: "var(--muted)", lineHeight: 1.5 }}>
              {t("아직 받은 과제가 없어요. 상담을 이어가면 목록이 채워져요.", "No tasks yet. Continue the conversation to build your task list.")}
            </div>
          )}
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} busy={taskBusy === task.id} onStart={startTask} locale={locale} />
          ))}
        </div>
        <div className="bottom-cta" style={{ paddingTop: 10, display: "flex", flexDirection: "column", gap: 10 }}>
          {toast && <div role="alert" className="capture-error" style={{ margin: 0 }}>{toast}</div>}
          <PrimaryButton onClick={returnToChat}>{t("상담으로 돌아가기", "Back to chat")}</PrimaryButton>
          {/* 화면 6~9(서류·승인·이력)로 들어가는 유일한 진입로다. */}
          <button type="button" onClick={() => go(7)} className="tap"
            style={{ width: "100%", minHeight: 46, borderRadius: 12, border: "1px solid var(--line)",
              background: "#fff", fontSize: 13.5, fontWeight: 700, color: "oklch(0.25 0.012 60)" }}>
            {t("내 신청서 · 서류함", "Applications · Documents")}
          </button>
        </div>
      </Shell>
    );
  }

  // ── 6 준비 안내 ──
  if (step === 6 && verdict) {
    const action = nextAction(verdict, locale);
    return (
      <Shell modal={activeModal}>
        <TopBar title={t("준비할 것", "What to prepare")} onBack={() => back(4)} />
        <Rail active={4} locale={locale} />
        <div style={{ padding: "4px 24px 16px" }}>
          <div style={{ padding: 17, borderRadius: 16, background: "#c44f40", color: "#fff" }}>
            <div style={{ ...mono, fontSize: 10.5, letterSpacing: "0.12em", textTransform: "uppercase", opacity: 0.85, marginBottom: 8 }}>{t("다음 할 일", "NEXT STEP")}</div>
            <div style={{ fontSize: 17, fontWeight: 800, lineHeight: 1.3 }}>{action.title}</div>
            <div style={{ fontSize: 13, lineHeight: 1.5, marginTop: 8, opacity: 0.92 }}>{action.meta}</div>
          </div>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ ...card, padding: 16 }}>
            <div style={{ fontSize: 15, fontWeight: 800 }}>{action.cardTitle}</div>
            <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 2 }}>{action.cardMeta}</div>
            <div style={{ marginTop: 11, display: "flex", flexDirection: "column", gap: 9 }}>
              {action.steps.map((s, i) => (
                <div key={i} style={{ display: "flex", gap: 10, fontSize: 12.5, lineHeight: 1.45, color: "oklch(0.35 0.012 60)" }}>
                  <span style={{ ...mono, color: "#c44f40", fontWeight: 700 }}>{i + 1}</span><span>{s}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 12, padding: "9px 11px", borderRadius: 9, background: "oklch(.93 .008 60)", fontSize: 11.5, lineHeight: 1.45 }}>{action.note}</div>
          </div>
        </div>
        <div className="bottom-cta">
          <PrimaryButton onClick={() => go(7)}>{t("내 신청서", "My applications")}</PrimaryButton>
        </div>
      </Shell>
    );
  }

  // ── 7 신청서 만들기 ──
  if (step === 7) {
    const taskApplicationIds = (agentState?.tasks || [])
      .map((task) => task.id)
      .filter((id) => APPLICATIONS[id]);
    const applicationIds = [...new Set(taskApplicationIds.length > 0 ? taskApplicationIds : [previewActionId])];
    if (!applicationIds.includes(previewActionId)) applicationIds.push(previewActionId);
    const selectedApplication = APPLICATIONS[previewActionId] || APPLICATIONS.open_bank_account;
    const goal = APPLICATION_GOALS[previewActionId] || APPLICATION_GOALS.open_bank_account;
    return <DocumentApplicationBuilder locale={locale} modal={activeModal} application={selectedApplication}
      goal={goal} documents={documents} loading={previewLoading} error={previewError}
      onBack={() => back(5)} onCreate={openPdfPreview} onOpenDocument={openStoredDocument} />;

    /* Legacy builder retained below until the next layout cleanup. */
    const alternatives = applicationIds.filter((actionId) => actionId !== previewActionId);
    return (
      <Shell modal={activeModal}>
        <TopBar title={t("신청서 만들기", "Create application")} onBack={() => back(verdict ? 6 : 5)} />
        <Rail active={4} locale={locale} />
        <div style={{ padding: "4px 24px 14px" }}>
          <h2 style={H2}>{t(`${selectedApplication.ko}를 만들게요`, `Let's create your ${selectedApplication.en.toLowerCase()}`)}</h2>
          <p style={SUB}>{t("목표 선택에서 고른 서류예요. 다시 고를 필요 없어요.", "This is the document you chose with your goal. No need to pick again.")}</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 11 }}>
          <div style={{ ...mono, fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--muted)" }}>
            {t("만들 서류 · 목표에서 확정", "Document · confirmed by goal")}
          </div>
          <div style={{ ...card, padding: 15, borderWidth: 1.5, borderColor: "var(--brand-2)", background: "oklch(0.72 0.13 45 / 0.06)" }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
              <b style={{ fontSize: 15.5 }}>{selectedApplication[locale]}</b>
              <span style={{ ...mono, fontSize: 10, fontWeight: 800, color: "var(--brand-2)", whiteSpace: "nowrap" }}>· {t("확정됨", "Confirmed")}</span>
            </div>
            <div style={{ marginTop: 6, fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45 }}>{goal[locale]}</div>
          </div>
          <div style={{ ...card, padding: 13, background: "oklch(0.95 0.006 60)", display: "flex", gap: 9 }}>
            <span aria-hidden="true" style={{ color: "var(--ok)", fontWeight: 800, fontSize: 12.5 }}>✓</span>
            <div style={{ fontSize: 11.5, lineHeight: 1.5, color: "oklch(0.4 0.012 60)" }}>
              {t("필요한 정보 확인됨 — 부족하면 챗봇이 물어봐요.", "Required information checked — the chatbot asks if anything is missing.")}
            </div>
          </div>
          {alternatives.length > 0 && (
            <details>
              <summary style={{ fontSize: 11.5, color: "var(--brand-2)", fontWeight: 700, cursor: "pointer" }}>
                {t("다른 서류 만들기", "Create a different document")}
              </summary>
              <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 7 }}>
                {alternatives.map((actionId) => (
                  <button key={actionId} type="button" onClick={() => setPreviewActionId(actionId)} className="tap"
                    style={{ minHeight: 42, padding: "9px 11px", borderRadius: 10, border: "1px solid var(--line)",
                      background: "#fff", color: "oklch(0.25 0.012 60)", textAlign: "left", fontWeight: 700 }}>
                    {APPLICATIONS[actionId][locale]}
                  </button>
                ))}
              </div>
            </details>
          )}
          {documents.map((d) => (
            <div key={d.id} style={{ ...card, display: "flex", gap: 13 }}>
              <div style={{ width: 52, height: 70, flex: "none", borderRadius: 7, border: "1px solid oklch(0.88 0.01 60)", background: "repeating-linear-gradient(0deg, oklch(0.9 0.01 60) 0 3px, oklch(0.97 0.008 60) 3px 9px)" }} />
              <div style={{ flex: 1 }}>
                <b style={{ fontSize: 14.5 }}>{d.title}</b>
                <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "'Noto Sans KR',sans-serif" }}>{formatDate(d.created_at, locale)}</div>
                <button type="button" onClick={() => openStoredDocument(d)} className="tap" style={{ marginTop: 10, padding: 0, border: 0, background: "transparent", color: "var(--brand-2)", fontSize: 11.5, fontWeight: 700 }}>{t("저장된 PDF 보기", "View saved PDF")}</button>
              </div>
            </div>
          ))}
        </div>
        <div className="bottom-cta">
          {previewError && <div role="alert" className="capture-error" style={{ margin: "0 0 10px" }}>{previewError}</div>}
          <PrimaryButton disabled={previewLoading} onClick={openPdfPreview}>
            {previewLoading ? t("신청서 만드는 중…", "Creating application…") : t("신청서 만들기", "Create application")}
          </PrimaryButton>
          <button type="button" onClick={() => { setCabinetBackStep(7); go(9); }} className="tap" style={{ width: "100%", marginTop: 9, minHeight: 46, borderRadius: 12, border: "1px solid var(--line)", background: "#fff", fontWeight: 700 }}>{t("내 서류함 · 발급 이력", "Documents · Issuance history")}</button>
        </div>
      </Shell>
    );
  }
  // ── 9 내 서류함 / 발급 이력 ──
  if (step === 9)
    return <DocumentCabinet locale={locale} modal={activeModal} documents={documents} ledger={ledger}
      loading={ledgerLoading} error={ledgerError} onBack={() => back(cabinetBackStep)}
      tasks={agentState?.tasks || []} sessionDrafts={sessionDrafts} currentSessionId={sessionId}
      onPreview={openStoredDocument} onDownload={downloadPdf} onStartChat={returnToChat}
      onOpenTask={openSavedWork} />;

  if (false && step === 9)
    return (
      <Shell modal={activeModal}>
        <TopBar title={t("내 서류함 · 발급 이력", "Documents · Issuance history")} onBack={() => back(cabinetBackStep)} />
        <div className="scroll" style={{ padding: "4px 20px 24px", display: "flex", flexDirection: "column", gap: 18 }}>
          <section>
            <h2 style={{ ...H2, fontSize: 20 }}>{t("저장 문서", "Saved documents")}</h2>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 9 }}>
              {documents.length === 0 && <div style={{ ...card, color: "var(--muted)", fontSize: 12.5 }}>{t("최근 응답에 저장된 문서가 없습니다.", "No saved documents yet.")}</div>}
              {documents.map((document) => (
                <div key={document.id} style={card}>
                  <b style={{ fontSize: 14 }}>{document.title}</b>
                  <div style={{ marginTop: 4, color: "var(--muted)", fontSize: 11.5 }}>{formatDate(document.created_at, locale)}</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <button type="button" onClick={() => openStoredDocument(document)} className="tap" style={smallActionStyle}>{t("미리보기", "Preview")}</button>
                    <button type="button" onClick={() => downloadPdf(document)} className="tap" style={smallActionStyle}>{t("PDF 다운로드", "Download PDF")}</button>
                  </div>
                </div>
              ))}
            </div>
          </section>
          <section>
            <h2 style={{ ...H2, fontSize: 20 }}>{t("발급 이력", "Issuance history")}</h2>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 9 }}>
              {ledgerLoading && <div style={{ ...card, color: "var(--muted)", fontSize: 12.5 }}>{t("불러오는 중…", "Loading…")}</div>}
              {ledgerError && <div role="alert" className="capture-error" style={{ margin: 0 }}>{ledgerError}</div>}
              {!ledgerLoading && !ledgerError && ledger.length === 0 && <div style={{ ...card, color: "var(--muted)", fontSize: 12.5 }}>{t("아직 발급한 서류가 없어요.", "No issued documents yet.")}</div>}
              {ledger.map((entry, index) => (
                <div key={`${entry.action || "action"}-${entry.approved_at || index}`} style={card}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><b>{entry.action || t("발급 서류", "Issued document")}</b><span style={{ ...mono, color: "var(--brand-2)", fontSize: 10.5 }}>{entry.risk_level}</span></div>
                  <div style={{ marginTop: 6, color: "var(--muted)", fontSize: 11.5 }}>{formatDate(entry.approved_at, locale)}</div>
                  {(entry.evidence || []).map((item) => <div key={item} style={{ marginTop: 6, fontSize: 11.5, color: "var(--muted)" }}>{t("근거", "Evidence")} · {item}</div>)}
                </div>
              ))}
            </div>
          </section>
        </div>
        {previewError && <div role="alert" className="capture-error" style={{ margin: "0 20px 12px" }}>{previewError}</div>}
      </Shell>
    );

  // ── PDF 뷰어 ──
  if (step === 10 && preview && previewBlobUrl) {
    const pageCount = Number(preview.page_count) > 0 ? Number(preview.page_count) : 0;
    const page = pageCount ? Math.min(Math.max(pdfPage, 1), pageCount) : 1;
    const dotStyle = (activeDot) => ({ width: 6, height: 6, borderRadius: 99, border: 0, padding: 0,
      background: activeDot ? "var(--brand-2)" : "oklch(0.55 0.01 60)" });
    const arrowStyle = { border: 0, background: "transparent", color: "oklch(0.78 0.01 60)", fontSize: 15, padding: "0 4px", lineHeight: 1 };
    return (
      <Shell modal={activeModal} dark>
        <TopBar title={preview.title} onBack={() => back(7)} />
        {(preview.warnings || []).length > 0 && (
          <div role="alert" style={{ margin: "0 20px 12px", padding: "11px 13px", borderRadius: 11, background: "oklch(.8 .1 75 / .15)", color: "oklch(.82 .08 75)", fontSize: 11.5, lineHeight: 1.5 }}>
            {preview.warnings.map((warning) => <div key={warning}>⚠ {warning}</div>)}
          </div>
        )}
        <div className="scroll" style={{ padding: "0 20px 12px" }}>
          <iframe title={preview.title} src={pageCount ? `${previewBlobUrl}#page=${page}` : previewBlobUrl}
            style={{ width: "100%", height: "100%", minHeight: 620, border: 0, borderRadius: 6, background: "#fff" }} />
        </div>
        {pageCount > 1 && (
          <div style={{ padding: "0 20px 4px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button type="button" className="tap" style={arrowStyle} aria-label="Previous page"
                disabled={page <= 1} onClick={() => setPdfPage(page - 1)}>‹</button>
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                {Array.from({ length: pageCount }, (_, i) => (
                  <button key={i} type="button" aria-label={`Page ${i + 1}`} aria-current={page === i + 1}
                    className="tap" style={dotStyle(page === i + 1)} onClick={() => setPdfPage(i + 1)} />
                ))}
              </div>
              <button type="button" className="tap" style={arrowStyle} aria-label="Next page"
                disabled={page >= pageCount} onClick={() => setPdfPage(page + 1)}>›</button>
            </div>
            <div style={{ ...mono, fontSize: 11, color: "oklch(0.78 0.01 60)" }}>{page} / {pageCount}</div>
          </div>
        )}
        <div className="bottom-cta" style={{ paddingTop: 12, paddingLeft: 20, paddingRight: 20, display: "flex", gap: 9 }}>
          <button type="button" onClick={() => downloadPdf(preview)} className="tap" style={{ ...smallActionStyle, minHeight: 52, fontSize: 13 }}>{t("PDF 다운로드", "Download PDF")}</button>
          {approval && <button type="button" onClick={() => setApprovalVisible(true)} className="tap" style={{ ...smallActionStyle, minHeight: 52, border: 0, fontSize: 14, color: "#fff", background: "var(--brand-2)" }}>{t("발급하기", "Issue")}</button>}
        </div>
      </Shell>
    );
  }
  return (
    <Shell modal={activeModal}>
      <TopBar title={t("다시 연결", "Reconnect")} onBack={() => back(0)} />
      <div style={{ padding: "28px 26px", display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 style={H2}>{t("화면을 다시 연결할게요", "Let's reconnect your screen")}</h2>
        <p style={SUB}>{t("진행 내용은 임시 저장되어 있어요. 이어하기를 눌러 안전하게 돌아가세요.", "Your progress is saved temporarily. Continue to return safely.")}</p>
        <PrimaryButton disabled={sessionLoading} onClick={resumeSession}>
          {sessionLoading ? t("불러오는 중…", "Loading…") : t("저장된 진행 이어하기", "Continue saved progress")}
        </PrimaryButton>
      </div>
    </Shell>
  );
}

// ── 작은 헬퍼 컴포넌트 ──
function DocumentTaskFlow({ tasks, answers, locale, modal, onBack, onReturnToChat, onOpen }) {
  const pick = (ko, en) => locale === "en" ? en : ko;
  const taskById = Object.fromEntries(tasks.map((task) => [task.id, task]));
  const steps = [
    { actionId: "alien_registration", title: pick("\ud1b5\ud569\uc2e0\uccad\uc11c", "Integrated application"), description: pick("\uc678\uad6d\uc778\ub4f1\ub85d \u2014 \uacc4\uc88c \uac1c\uc124\uc758 \uc120\ud589 \uc11c\ub958", "Alien registration \u2014 required before opening an account") },
    { actionId: "open_bank_account", title: pick("\uacc4\uc88c\uac1c\uc124\uc2e0\uccad\uc11c", "Bank account application"), description: pick("\ucd5c\uc885 \ubaa9\ud45c \u2014 \uc740\ud589 \uc601\uc5c5\uc810 \uc81c\ucd9c\uc6a9", "Final goal \u2014 for submission at a bank branch") },
  ];
  return <Shell modal={modal}>
    <TopBar title={pick("\ud560 \uc77c", "Tasks")} onBack={onBack} />
    <Rail active={3} locale={locale} />
    <div className="document-flow-head"><h2>{pick("\uacc4\uc88c \uac1c\uc124\uae4c\uc9c0 \uc11c\ub958 2\uac1c", "Two documents to open your account")}</h2><p>{pick("\uacc4\uc88c\ub97c \ub9cc\ub4e4\ub824\uba74 \uba3c\uc800 \uc678\uad6d\uc778\ub4f1\ub85d\uc774 \ub418\uc5b4 \uc788\uc5b4\uc57c \ud574\uc694. \uadf8\ub798\uc11c \ub450 \uc11c\ub958\ub97c \uc21c\uc11c\ub300\ub85c \ub9cc\ub4e4\uc5b4 \ub4dc\ub824\uc694.", "You need alien registration first. We will prepare both documents in order.")}</p></div>
    <div className="scroll document-flow-list">
      {steps.map((item, index) => { const status = taskById[item.actionId]?.status; const done = status === "done"; const active = status === "in_progress" || status === "available"; return <React.Fragment key={item.actionId}>
        {index > 0 && <div className="document-flow-arrow">{"\u2193"}</div>}
        <section className={`document-flow-card${active ? " active" : ""}`}><div className="document-flow-row"><span className="document-flow-number">{index + 1}</span><div><b>{item.title}</b><p>{item.description}</p></div><em>{done ? pick("\uc644\ub8cc", "Done") : status === "in_progress" ? pick("\uc791\uc131 \uc911", "In progress") : status === "available" ? pick("\uc2dc\uc791 \uac00\ub2a5", "Ready") : pick("\uc120\ud589 \ud544\uc694", "Locked")}</em></div>{active && <button type="button" onClick={() => onOpen(item.actionId)}>{status === "in_progress" ? pick("\uc774\uc5b4\ud558\uae30", "Continue") : pick("\uc2dc\uc791\ud558\uae30", "Start")}</button>}{item.actionId === "open_bank_account" && <div className="document-card-requirements"><div className="document-ready-label">{pick("\uc0c1\ub2f4\uc5d0\uc11c \ud655\uc778\ud55c \uc900\ube44\ubb3c", "Items confirmed in chat")}</div><div className="document-ready-chips"><span className={answers.phone === "yes" ? "ready" : ""}>{answers.phone === "yes" ? "\u2713 " : ""}{pick("\ud734\ub300\ud3f0", "Mobile phone")}</span><span className={answers.cert === "yes" ? "ready" : ""}>{answers.cert === "yes" ? "\u2713 " : ""}{pick("\uc7ac\ud559\uc99d\uba85\uc11c", "Enrollment certificate")}</span></div></div>}</section>
      </React.Fragment>; })}
    </div>
    <button type="button" className="task-chat-fab tap" onClick={onReturnToChat}
      aria-label={pick("AI \uc0c1\ub2f4\uc73c\ub85c \ub3cc\uc544\uac00\uae30", "Back to AI chat")}>
      <span><b>{pick("AI \uc0c1\ub2f4", "AI chat")}</b><small>{pick("\uc0c1\ub2f4\uc73c\ub85c \ub3cc\uc544\uac00\uae30", "Back to chat")}</small></span>
      <img src="/assets/dari-mascot.png" alt="" />
    </button>
  </Shell>;
}

function DocumentApplicationBuilder({ locale, modal, application, goal, documents, loading, error, onBack, onCreate, onOpenDocument }) {
  const pick = (ko, en) => locale === "en" ? en : ko;
  return <Shell modal={modal}>
    <TopBar title={pick("\uc2e0\uccad\uc11c \ub9cc\ub4e4\uae30", "Create application")} onBack={onBack} /><Rail active={4} locale={locale} />
    <div className="builder-head"><h2>{pick(`${application.ko}\ub97c \ub9cc\ub4e4\uac8c\uc694`, `Let's create your ${application.en.toLowerCase()}`)}</h2><p>{pick("\uc800\uc7a5\ub41c \ud504\ub85c\ud544\ub85c \uc790\ub3d9 \uc791\uc131\ud574\uc694. \ub9cc\ub4e4\uae30\ub97c \ub204\ub974\uba74 \ubbf8\ub9ac\ubcf4\uae30\uac00 \ub098\uc640\uc694.", "We fill it automatically from your saved profile. Create it to see a preview.")}</p></div>
    <div className="scroll builder-content"><section className="builder-selection"><div><b>{application[locale]}</b><span>✓ {pick("\ud655\uc815\ub428", "Confirmed")}</span></div><p>{goal[locale]}</p></section>{loading ? <DocumentWritingProgress locale={locale} title={application[locale]} /> : <div className="document-paper-preview"><i /><i /><i /><i /><i /><div /></div>}{documents.filter((doc) => doc.title === application[locale]).map((doc) => <button key={doc.id} type="button" className="stored-document-link" onClick={() => onOpenDocument(doc)}>{pick("\uc800\uc7a5\ub41c PDF \ubcf4\uae30", "View saved PDF")}</button>)}</div>
    <div className="builder-actions">{error && <div role="alert" className="capture-error">{error}</div>}<button type="button" disabled={loading} onClick={onCreate}>{loading ? pick("\uc2e0\uccad\uc11c \ub9cc\ub4dc\ub294 \uc911\u2026", "Creating application\u2026") : pick("\uc2e0\uccad\uc11c \ub9cc\ub4e4\uae30", "Create application")}</button></div>
  </Shell>;
}

function DocumentCabinet({ locale, modal, documents: rawDocuments, ledger: rawLedger, loading, error, tasks = [], sessionDrafts = [], currentSessionId, onBack, onPreview, onDownload, onStartChat, onOpenTask }) {
  const pick = (ko, en) => locale === "en" ? en : ko;
  const documents = [...rawDocuments]
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))
    .filter((document, index, all) => all.findIndex((candidate) =>
      (candidate.action_id || candidate.title) === (document.action_id || document.title)) === index);
  const ledger = [...rawLedger]
    .sort((a, b) => String(b.approved_at || "").localeCompare(String(a.approved_at || "")))
    .filter((entry, index, all) => all.findIndex((candidate) =>
      `${candidate.document_id || candidate.action}:${candidate.approved_at || ""}` ===
      `${entry.document_id || entry.action}:${entry.approved_at || ""}`) === index)
    .slice(0, 5);
  const draftSources = [{ sessionId: currentSessionId, tasks }, ...sessionDrafts
    .filter((draft) => draft.sessionId !== currentSessionId)];
  const seenWorks = new Set();
  const pendingWorks = draftSources.flatMap((draft) => (draft.tasks || []).map((task) => ({
    ...task,
    status: ["residence_change", "work_activity"].includes(task.id) ? "locked" : task.status,
    sessionId: draft.sessionId,
  }))).filter((task) => {
    const key = task.id;
    if (!APPLICATIONS[task.id] || seenWorks.has(key)) return false;
    seenWorks.add(key);
    const hasDocument = documents.some((document) => document.action_id === task.id
      && (!document.session_id || document.session_id === task.sessionId));
    return !hasDocument && task.status === "in_progress";
  });
  return <Shell modal={modal}><TopBar title={pick("\ub0b4 \uc11c\ub958\ud568 \u00b7 \ubc1c\uae09 \uc774\ub825", "Documents \u00b7 Issuance history")} onBack={onBack} /><div className="scroll cabinet-content">
    <section><h2>{pick("\uc800\uc7a5 \ubb38\uc11c", "Saved documents")} <small>{documents.length + pendingWorks.length}</small></h2>{documents.length === 0 && pendingWorks.length === 0 ? <div className="cabinet-zero"><img src="/assets/dari-mascot.png" alt="" /><h3>{pick("\uc544\uc9c1 \uc800\uc7a5\ub41c \uc11c\ub958\uac00 \uc5c6\uc5b4\uc694", "No saved documents yet")}</h3><p>{pick("AI \uc0c1\ub2f4\uc5d0\uc11c \ud544\uc694\ud55c \uc11c\ub958\ub97c \ud655\uc778\ud558\uace0 \uc2e0\uccad\uc11c\ub97c \ub9cc\ub4e4\uc5b4 \ubcf4\uc138\uc694.", "Ask the AI what you need and create your first application.")}</p><button type="button" onClick={onStartChat}>{pick("AI \uc0c1\ub2f4\uc5d0\uc11c \uc2dc\uc791\ud558\uae30", "Start in AI chat")}</button></div> : <div className="cabinet-list saved-work-list">{pendingWorks.map((task, index) => <article key={`${task.sessionId}-${task.id}`}><div><span>{index + 1}</span><b>{APPLICATIONS[task.id][locale]}</b><em className={`work-status ${task.status}`}>{task.status === "in_progress" ? pick("\uc791\uc131 \uc911", "In progress") : task.status === "available" ? pick("\uc2dc\uc791 \uac00\ub2a5", "Ready") : pick("🔒 \uc7a0\uae08", "🔒 Locked")}</em></div><p>{task.note || task.agency}</p>{task.status !== "locked" && <button type="button" className="saved-work-action" onClick={() => onOpenTask(task.sessionId, task.id)}>{task.status === "in_progress" ? pick("\uc774\uc5b4\ud558\uae30", "Continue") : pick("\uc2dc\uc791\ud558\uae30", "Start")}</button>}</article>)}{documents.map((doc, index) => <article key={doc.id}><div><span>{pendingWorks.length + index + 1}</span><b>{doc.title}</b><em className={`work-status ${doc.status === "issued" ? "issued" : "done"}`}>{doc.status === "issued" ? pick("\ubc1c\uae09 \uc644\ub8cc", "Issued") : pick("\uc791\uc131 \uc644\ub8cc", "Completed")}</em></div><p>{formatDate(doc.created_at, locale)}</p><div className="cabinet-buttons"><button type="button" onClick={() => onPreview(doc)}>{pick("\ubbf8\ub9ac\ubcf4\uae30", "Preview")}</button><button type="button" onClick={() => onDownload(doc)}>PDF {pick("\ub2e4\uc6b4\ub85c\ub4dc", "Download")}</button></div></article>)}</div>}</section>
    <section><h2>{pick("\ubc1c\uae09 \ubb38\uc11c \u00b7 \uc774\ub825", "Issued documents \u00b7 History")}</h2>{loading && <div className="cabinet-empty">{pick("\ubd88\ub7ec\uc624\ub294 \uc911\u2026", "Loading\u2026")}</div>}{error && <div className="capture-error">{error}</div>}{!loading && !error && ledger.length === 0 ? <div className="history-zero"><span aria-hidden="true">✓</span><div><b>{pick("\uc544\uc9c1 \ubc1c\uae09\ud55c \ubb38\uc11c\uac00 \uc5c6\uc5b4\uc694", "No issued documents yet")}</b><p>{pick("\ubbf8\ub9ac\ubcf4\uae30 \ud6c4 \ucd5c\uc885 \ubc1c\uae09\uae4c\uc9c0 \uc2b9\uc778\ud55c \ubb38\uc11c\ub9cc \uc5ec\uae30\uc5d0 \ub0a8\uc544\uc694.", "Only documents you finally approve for issuance appear here.")}</p></div></div> : <div className="cabinet-list history-list">{ledger.map((entry, index) => <article key={`${entry.document_id || entry.action}-${entry.approved_at || index}`}><b>{entry.action || pick("\uc2e0\uccad\uc11c \ubc1c\uae09", "Application issued")}</b><p>{formatDate(entry.approved_at, locale)}</p><small>{pick("\ucd5c\uc885 \ubc1c\uae09 \uc644\ub8cc", "Issuance completed")}</small></article>)}</div>}</section>
  </div></Shell>;
}

function DocumentWritingProgress({ locale = "ko", title }) {
  const en = locale === "en";
  const [phase, setPhase] = useState(0);
  const phases = en
    ? ["Checking your profile", "Filling the required fields", "Preparing the PDF preview"]
    : ["프로필을 확인하고 있어요", "신청서 항목을 채우고 있어요", "PDF 미리보기를 준비하고 있어요"];
  useEffect(() => {
    const interval = window.setInterval(() => setPhase((current) => (current + 1) % phases.length), 1400);
    return () => window.clearInterval(interval);
  }, [phases.length]);
  return <div className="document-writing-progress" role="status" aria-live="polite">
    <div className="writing-paper" aria-hidden="true"><i /><i /><i /><i /><span /></div>
    <b>{en ? `Creating ${title}` : `${title} 작성 중`}</b>
    <p key={phase}>{phases[phase]}<i aria-hidden="true">...</i></p>
    <small>{en ? "Please keep this screen open for a moment." : "잠시만 기다려 주세요. 완성되면 바로 미리보기를 열어드려요."}</small>
  </div>;
}

function Shell({ children, dark, modal }) {
  return (
    <div className="app-shell device-preview">
      <div className={`phone${dark ? " dark" : ""}`}>{children}{modal}</div>
    </div>
  );
}
function Label({ children }) {
  return <div style={{ padding: "6px 0", ...mono, fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)" }}>{children}</div>;
}
function CitationList({ line, locale }) {
  const sourceText = line.replace(/^(\uadfc\uac70|Sources?)\s*\u00b7\s*/i, "");
  const sources = sourceText.split(" / ").map((source) => source.trim()).filter(Boolean);
  return <aside className="chat-citations" aria-label={locale === "en" ? "Sources" : "근거 자료"}>
    <b><span aria-hidden="true">§</span>{locale === "en" ? "Sources" : "확인한 근거"}</b>
    <ul>{sources.map((source, index) => <li key={`${source}-${index}`}>{source}</li>)}</ul>
  </aside>;
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
function CaptureProgress({ locale = "ko" }) {
  const en = locale === "en";
  const [phase, setPhase] = useState(0);
  const phases = en
    ? ["Sending image securely", "Reading the text", "Organizing the details"]
    : ["이미지를 안전하게 보내고 있어요", "글자를 하나씩 읽고 있어요", "필요한 정보를 정리하고 있어요"];
  useEffect(() => {
    const interval = window.setInterval(() => setPhase((current) => (current + 1) % phases.length), 1500);
    return () => window.clearInterval(interval);
  }, [phases.length]);
  return (
    <div className="capture-progress" role="status" aria-live="polite">
      <div className="ai-reading-mark" aria-hidden="true">
        <span className="ai-reading-label">AI</span>
        <span className="reading-line line-one"><i /></span>
        <span className="reading-line line-two"><i /></span>
        <span className="reading-line line-three"><i /></span>
      </div>
      <b>{en ? "AI is reading your document" : "AI가 서류를 읽고 있어요"}</b>
      <span className="scan-status" key={phase}>{phases[phase]}<i aria-hidden="true">...</i></span>
      <small>{en ? "This may take a moment. Please keep this screen open." : "잠시 걸릴 수 있어요. 화면을 그대로 두세요."}</small>
    </div>
  );
}
function AuthInput({ label, type = "text", value, onChange, placeholder, valid, indicator = "✓", ...inputProps }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 7 }}>
      <span style={{ fontSize: 12.5, fontWeight: 700 }}>{label}</span>
      <span style={{ position: "relative", display: "block" }}>
        <input className={`auth-input${valid ? " valid" : ""}`} type={type} value={value} onChange={onChange} placeholder={placeholder} {...inputProps}
          style={{ width: "100%", height: 54, border: "1px solid var(--line)", borderRadius: 13, padding: valid ? "0 46px 0 15px" : "0 15px", outline: "none", background: "#fff", color: "var(--ink)", font: "inherit", fontSize: 15 }} />
        {valid && <span className="auth-input-indicator" aria-hidden="true">{indicator}</span>}
      </span>
    </label>
  );
}
function FieldHint({ children, tone = "info" }) {
  return <div className={`auth-field-hint ${tone}`}>{children}</div>;
}
function ChatBubble({ children, mine, avatar, wide, compact }) {
  return (
    <div className={`chat-line${mine ? " mine" : ""}${wide ? " wide" : ""}${compact ? " compact" : ""}`}>
      {avatar && <div className="chat-avatar" aria-hidden="true"><img src="/assets/dari-avatar.png" alt="" /></div>}
      <div className="chat-bubble">{children}</div>
    </div>
  );
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
function ExitButton({ onClick, locale = "ko" }) {
  return <button type="button" onClick={onClick} className="exit-button">{locale === "en" ? "Exit" : "나가기"}</button>;
}
function LangToggle({ locale = "ko", onChange }) {
  return (
    <div className="lang-toggle" role="group" aria-label={locale === "en" ? "Language" : "언어 선택"}>
      <button type="button" className={locale === "ko" ? "on" : ""} aria-pressed={locale === "ko"} onClick={() => onChange("ko")}>한</button>
      <button type="button" className={locale === "en" ? "on" : ""} aria-pressed={locale === "en"} onClick={() => onChange("en")}>EN</button>
    </div>
  );
}
function TopActions({ locale, onLocale, onExit }) {
  return (
    <div className="top-actions">
      <LangToggle locale={locale} onChange={onLocale} />
      <ExitButton onClick={onExit} locale={locale} />
    </div>
  );
}
function LanguageChoice({ title, subtitle, selected, onClick }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={selected} className={`language-choice${selected ? " selected" : ""}`}>
      <b>{title}</b>
      <span className="language-sub">{subtitle}</span>
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
function ChatInputBar({ value, onChange, disabled, onSend, locale = "ko" }) {
  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSend();
    }
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSend(); }} className="chat-input-bar">
      <input
        type="text"
        className="chat-input-field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKey}
        placeholder={locale === "en" ? "Type your message" : "메시지를 입력하세요"}
        disabled={disabled}
        autoComplete="off"
      />
      <button type="submit" className="chat-send-btn tap" disabled={disabled || !value.trim()}>
        {disabled ? "…" : locale === "en" ? "Send" : "전송"}
      </button>
    </form>
  );
}
function ExitConfirmModal({ onContinue, onExit, locale = "ko" }) {
  const en = locale === "en";
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="exit-title" className="modal-backdrop">
      <div className="exit-dialog">
        <div className="exit-dialog-icon" aria-hidden="true">☁</div>
        <h3 id="exit-title">{en ? "Pause for now?" : "진행을 잠시 멈출까요?"}</h3>
        <p>{en ? "Photos are not stored in your browser. Only your progress is saved temporarily on this device, and your server profile is restored after you sign in again." : "사진 자체는 브라우저에 보관하지 않고, 진행 단계만 이 기기에 임시 저장해요. 다음에 로그인하면 서버에 저장된 프로필로 이어갈 수 있어요."}</p>
        <div className="exit-dialog-actions">
          <button type="button" onClick={onContinue} className="tap">{en ? "Keep going" : "계속 진행"}</button>
          <button type="button" onClick={onExit} className="tap primary">{en ? "Save and exit" : "저장하고 나가기"}</button>
        </div>
      </div>
    </div>
  );
}
function NewDocumentConfirmModal({ onContinue, onStart, loading, locale = "ko" }) {
  const en = locale === "en";
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="new-document-title" className="modal-backdrop">
      <div className="exit-dialog new-document-dialog">
        <div className="exit-dialog-icon" aria-hidden="true">↻</div>
        <h3 id="new-document-title">{en ? "Prepare another document?" : "다른 서류도 준비할까요?"}</h3>
        <p>{en
          ? "Your current work will be paused, not deleted. You can return later and continue from the remaining question."
          : "현재 작업은 삭제되지 않고 작성 중으로 저장돼요. 나중에 다시 열면 남은 질문부터 이어할 수 있어요."}</p>
        <div className="new-document-preserved"><span aria-hidden="true">✓</span><div><b>{en ? "Progress saved" : "진행 상태 저장"}</b><small>{en ? "Answers · Profile · Issued documents" : "작성한 답변 · 프로필 · 발급 서류"}</small></div></div>
        <div className="exit-dialog-actions">
          <button type="button" disabled={loading} onClick={onContinue} className="tap">{en ? "Continue current work" : "기존 작업 이어하기"}</button>
          <button type="button" disabled={loading} onClick={onStart} className="tap primary">{loading ? (en ? "Starting…" : "새 상담 여는 중…") : (en ? "Start new consultation" : "새 상담 시작")}</button>
        </div>
      </div>
    </div>
  );
}
function ApprovalModal({ approval, loading, error, onDecision, locale = "ko" }) {
  const en = locale === "en";
  const label = approval.title || (en ? "this action" : "이 작업");
  return (
    <div role="dialog" aria-modal="true" aria-label={en ? "Action approval" : "실행 승인"}
      className="approval-backdrop" style={{ position: "absolute", inset: 0, zIndex: 20, background: "oklch(0.2 0.012 60 / 0.55)", display: "flex", alignItems: "center", justifyContent: "center", padding: "0 22px" }}>
      <div className="approval-sheet" style={{ width: "100%", padding: "20px 20px 18px", borderRadius: 20, background: "#fff", boxShadow: "0 18px 44px oklch(0.2 0.012 60 / 0.28)" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 99, background: "oklch(0.72 0.13 45 / 0.12)" }}>
          <span aria-hidden="true" style={{ width: 6, height: 6, borderRadius: 99, background: "var(--brand-2)" }} />
          <span style={{ fontSize: 10.5, fontWeight: 800, color: "var(--brand-2)" }}>
            {en ? "Now: confirm issuance" : "지금: 발급 확인"}
          </span>
        </div>
        <h3 style={{ margin: "12px 0 10px", fontSize: 19, lineHeight: 1.32 }}>
          {en ? `Issue your ${label.toLowerCase()}?` : `${label}를 발급할까요?`}
        </h3>
        <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55, color: "oklch(0.35 0.012 60)" }}>
          {en
            ? <>The preview above is an already generated PDF. Issuing it saves the document to your document box.</>
            : <>위 미리보기는 <b>이미 작성된 PDF</b>예요. 발급을 누르면 서류함에 확정 저장돼요.</>}
        </p>
        {(approval.summary || []).map((item) => (
          <div key={item} style={{ marginTop: 7, fontSize: 12, color: "oklch(0.35 0.012 60)" }}>· {item}</div>
        ))}
        {(approval.evidence || []).map((item) => (
          <div key={item} style={{ marginTop: 5, fontSize: 11.5, color: "var(--muted)" }}>{en ? "Evidence" : "근거"} · {item}</div>
        ))}
        <p style={{ margin: "12px 0 0", fontSize: 12.5, lineHeight: 1.5, color: "oklch(0.35 0.012 60)" }}>
          {en ? "This app prepares the document for you. Submit the printed copy yourself at the bank or immigration office." : "이 앱은 서류를 만들어 드려요. 은행·출입국관리소 제출은 직접 해야 해요."}
        </p>
        <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--muted)" }}>
          {en ? "You can issue it again at any time." : "언제든 다시 발급할 수 있어요."}
        </p>
        {error && <div role="alert" className="capture-error" style={{ margin: "12px 0 0" }}>{error}</div>}
        <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
          <button type="button" disabled={loading} onClick={() => onDecision(false)} className="tap" style={{ minHeight: 48, borderRadius: 13, border: "1px solid var(--line)", background: "#fff", fontWeight: 700 }}>{en ? "Cancel" : "취소"}</button>
          <button type="button" disabled={loading} onClick={() => onDecision(true)} className="tap" style={{ minHeight: 48, borderRadius: 13, border: 0, background: "var(--brand-2)", color: "#fff", fontWeight: 700 }}>{loading ? (en ? "Issuing…" : "발급 중…") : (en ? "Issue" : "발급하기")}</button>
        </div>
      </div>
    </div>
  );
}
const smallActionStyle = { flex: 1, minHeight: 38, borderRadius: 10, border: "1px solid var(--line)", background: "#fff", fontSize: 11.5, fontWeight: 700 };

function formatDate(value, locale = "ko") {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(locale === "en" ? "en-US" : "ko-KR");
}
// 촬영 화면 오류 문구. 계약의 error code 별로 다음 행동을 다르게 안내한다.
function localizedText(value, locale, englishFallback) {
  const text = value ? String(value) : "";
  return locale === "en" && /[가-힣]/.test(text) ? englishFallback : text || englishFallback;
}

function localizedError(error, locale, koreanFallback, englishFallback) {
  if (locale !== "en") return error instanceof Error && error.message ? error.message : koreanFallback;
  const byCode = {
    invalid_or_missing_token: "Your login has expired. Please sign in again.",
    session_access_denied: "You cannot access this session. Please sign in again.",
    prerequisite_missing: "Complete the required task first.",
    extraction_failed: "We could not read the image. Please try again.",
    validation_failed: "Check the information you entered.",
    blocked_by_law: "This step cannot proceed due to legal requirements.",
    network: "Could not connect to the network. Please try again.",
  };
  if (byCode[error?.code]) return byCode[error.code];
  return localizedText(error instanceof Error ? error.message : "", locale, englishFallback);
}

function captureMessage(error, locale = "ko") {
  const en = locale === "en";
  switch (error?.code) {
    case "extraction_failed":
      return en ? "We could not read the image. Avoid glare and capture the entire document." : "사진에서 정보를 읽지 못했어요. 빛 반사를 피해 카드 전체가 보이게 다시 촬영해 주세요.";
    case "unsupported_media_type":
      return en ? "Only PNG images are supported. Retake the photo to convert it automatically." : "PNG 이미지만 올릴 수 있어요. 다시 촬영하면 자동으로 PNG로 변환돼요.";
    case "upload_not_completed":
      return en ? "The upload did not finish. Please try again." : "사진 업로드가 끝나지 않았어요. 다시 촬영해 주세요.";
    case "network":
      return en ? "Could not connect to the network. Please try again." : "네트워크에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.";
    default:
      return localizedError(error, locale, "이미지를 처리하지 못했어요.", "Could not process the image.");
  }
}

// 신원 불일치 항목의 값. 국적·성별은 코드로 오므로 사람이 읽는 말로 바꾼다.
function mismatchValue(key, value, locale = "ko") {
  const en = locale === "en";
  if (!value) return en ? "none" : "없음";
  // 한글 국가명 맵은 8개국뿐이다. 영어는 서류(MRZ)에 찍힌 코드를 그대로 쓴다.
  if (key === "nationality") return en ? value : nationalityLabel(value);
  if (key === "gender") return (GENDER_LABELS[value] || [value, value])[en ? 1 : 0];
  return String(value);
}

function CaptureAlert({ error, locale = "ko", onDeviceCamera, onReviewEarlier }) {
  const en = locale === "en";
  if (!error) return null;
  const mismatch = error.code === "validation_failed";
  const parsingFailed = error.code === "extraction_failed";
  const mismatched = Object.entries(error.details?.mismatched || {});
  return (
    <div className="capture-alert-backdrop">
      <div role="alertdialog" aria-modal="true" className="capture-alert-dialog">
        <div className={`capture-alert-icon${mismatch ? " warning" : " error"}`} aria-hidden="true">{mismatch ? "⚠" : "⊘"}</div>
        <h3>{mismatch
          ? (en ? "The photo details do not match" : "사진 정보가 서로 일치하지 않아요")
          : parsingFailed
            ? (en ? "We could not read the photo" : "사진을 읽을 수 없어요")
            : (en ? "We could not process the photo" : "사진을 처리할 수 없어요")}</h3>
        <p>{mismatch
          ? (en ? "Check that all images belong to the same person and attach them again. You cannot continue until they match." : "3장이 같은 사람의 정보인지 확인하고 다시 첨부해 주세요. 일치 전까지 다음 단계로 넘어가지 않아요.")
          : error.message}</p>
        {mismatched.length > 0 && (
          <div className="capture-alert-details">
            {mismatched.map(([key, pair]) => <span key={key}>{profileFieldLabel({ key }, locale)} · {mismatchValue(key, pair?.existing, locale)} → {mismatchValue(key, pair?.incoming, locale)}</span>)}
          </div>
        )}
        {parsingFailed && <code>extraction_failed {en ? "(unreadable)" : "(파싱 불가)"}</code>}
        <button type="button" onClick={mismatch ? onReviewEarlier : onDeviceCamera}>
          {mismatch ? (en ? "Attach again" : "다시 첨부하기") : (en ? "Retake photo" : "다시 촬영하기")}
        </button>
      </div>
    </div>
  );
}

function profileFieldLabel(field, locale = "ko") {
  const labels = {
    name_en: ["이름", "Name"],
    arc_no: ["등록번호", "Registration number"],
    nationality: ["국적", "Nationality"],
    visa_type: ["체류자격", "Visa type"],
    stay_expiry: ["체류기간", "Stay expiry"],
    addr_kr: ["체류지", "Address in Korea"],
    birth_date: ["생년월일", "Date of birth"],
    gender: ["성별", "Sex"],
  };
  const label = labels[field?.key];
  if (label) return label[locale === "en" ? 1 : 0];
  if (locale === "en") return String(field?.key || "Field").replaceAll("_", " ");
  return field?.label || field?.key || "";
}

function verdictCta(kind, locale = "ko") {
  const labels = locale === "en"
    ? { ready: "What should I bring?", passport: "How do I renew it?", phone: "How do I get a phone?", cert: "Where can I get it?" }
    : { ready: "무엇을 가져가나요?", passport: "어떻게 재발급하나요?", phone: "휴대폰은 어떻게 개통하나요?", cert: "어디서 떼나요?" };
  return labels[kind] || (locale === "en" ? "View next step" : "다음 단계 보기");
}
function nextAction(v, locale = "ko") {
  if (locale === "en") {
    if (v.kind === "passport")
      return { title: "Renew your passport before visiting the bank", meta: "Embassy in Korea · 1–3 weeks · Residence card unaffected",
        cardTitle: "Passport renewal", cardMeta: "Current passport · Residence card · Embassy visit",
        note: "Return to the app when your new passport is issued. We will prepare the documents again.",
        steps: ["Book an appointment with your embassy in Korea.", "Bring your residence card and current passport.", "Return to the app after receiving the new passport number."] };
    if (v.kind === "phone")
      return { title: "Get a prepaid phone in your name", meta: "Any mobile carrier store · Bring residence card and passport · Same-day activation",
        cardTitle: "Phone activation", cardMeta: "Must be in your name · Prepaid MVNO plans accepted",
        note: "A number registered to a friend cannot be used. It must be in your name.",
        steps: ["Bring your residence card and passport to a mobile carrier store.", "Ask for a prepaid plan; a Korean bank account is not required.", "Make sure the number is registered in your name."] };
    if (v.kind === "cert")
      return { title: "Print your enrollment certificate", meta: "School portal or international office · Paper original · Issued within 3 months",
        cardTitle: "Enrollment certificate", cardMeta: "Enrollment certificate or admission letter · Issued by your school",
        note: "We do not scan this document. Bring the paper original for the bank to check.",
        steps: ["Sign in to your school portal and print the certificate.", "If classes have not started, use your admission letter instead.", "Bring the paper original issued within the last 3 months."] };
    return { title: "Visit the bank with your documents", meta: "Residence card, passport, enrollment certificate, and printed application",
      cardTitle: "Enrollment certificate", cardMeta: "Enrollment certificate or admission letter · Issued by your school",
      note: "We do not scan this document. Bring the paper original for the bank to check.",
      steps: ["Print it from your school portal or contact the international office.", "Bring the paper original issued within the last 3 months.", "If classes have not started, use your admission letter instead."] };
  }
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
