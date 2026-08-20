// 여러 화면이 공유하는 작은 UI 조각들.
import React from "react";

export function BridgeMark({ size = 60, bg = "oklch(0.97 0.01 250)" }) {
  return (
    <div style={{ width: size, height: size, borderRadius: size * 0.27, background: bg,
      display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width={size * 0.58} height={size * 0.58} viewBox="0 0 96 96" fill="none">
        <circle cx="24" cy="34" r="9" fill="oklch(0.7 0.13 45)" />
        <circle cx="72" cy="34" r="9" fill="oklch(0.55 0.14 250)" />
        <path d="M18 62c0-16.6 13.4-30 30-30s30 13.4 30 30" stroke="oklch(0.55 0.14 250)" strokeWidth="6.5" strokeLinecap="round" fill="none" />
        <line x1="48" y1="32" x2="48" y2="62" stroke="oklch(0.55 0.14 250)" strokeWidth="6.5" strokeLinecap="round" />
        <line x1="33" y1="42" x2="33" y2="62" stroke="oklch(0.55 0.14 250)" strokeWidth="5" strokeLinecap="round" />
        <line x1="63" y1="42" x2="63" y2="62" stroke="oklch(0.55 0.14 250)" strokeWidth="5" strokeLinecap="round" />
      </svg>
    </div>
  );
}

// MAITE 표기용 워드마크. 이미지 에셋이 없어도 철자와 비율이 흔들리지 않도록
// 한 컴포넌트에서만 렌더링한다.
export function MaiteWordmark({ compact = false, inverse = false }) {
  return (
    <div className={`maite-wordmark${compact ? " compact" : ""}${inverse ? " inverse" : ""}`} aria-label="MAITE">
      <span>MAI</span>
      <svg viewBox="0 0 34 32" aria-hidden="true">
        <path d="M5 7h24M17 7v18" />
        <circle cx="5" cy="7" r="3.2" />
        <circle cx="29" cy="7" r="3.2" />
        <circle cx="17" cy="25" r="3.2" />
      </svg>
      <span>E</span>
    </div>
  );
}

// 상담 화면 전용 MAITE 연결 모티프 캐릭터.
export function MaiteAvatar({ size = 36 }) {
  return (
    <div className="maite-avatar" style={{ width: size, height: size, borderRadius: size * 0.32 }} aria-label="MAITE AI">
      <svg width={size * 0.72} height={size * 0.72} viewBox="0 0 48 48" fill="none" aria-hidden="true">
        <path d="M12 15h24M24 15v18" />
        <circle cx="12" cy="15" r="5" />
        <circle cx="36" cy="15" r="5" />
        <circle cx="24" cy="33" r="5" />
        <circle cx="21" cy="24" r="1.7" className="maite-eye" />
        <circle cx="27" cy="24" r="1.7" className="maite-eye" />
      </svg>
    </div>
  );
}

// 재방문 홈 화면(step 0, 로그인 상태) 전용 — 은행 건물 + 원화 배지.
export function BankMark({ size = 60, bg = "oklch(0.97 0.01 250)" }) {
  return (
    <div style={{ width: size, height: size, borderRadius: size * 0.27, background: bg,
      display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
      <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 96 96" fill="none">
        <path d="M48 14 14 34h68z" fill="oklch(0.55 0.14 250)" />
        <rect x="14" y="40" width="68" height="6" rx="1.5" fill="oklch(0.55 0.14 250)" />
        <rect x="18" y="48" width="6" height="26" fill="oklch(0.55 0.14 250)" />
        <rect x="33" y="48" width="6" height="26" fill="oklch(0.55 0.14 250)" />
        <rect x="48" y="48" width="6" height="26" fill="oklch(0.55 0.14 250)" />
        <rect x="63" y="48" width="6" height="26" fill="oklch(0.55 0.14 250)" />
        <rect x="78" y="48" width="6" height="26" fill="oklch(0.55 0.14 250)" />
        <rect x="12" y="78" width="72" height="6" rx="1.5" fill="oklch(0.55 0.14 250)" />
      </svg>
      <span aria-hidden="true" style={{
        position: "absolute", top: size * 0.06, right: size * 0.06,
        width: size * 0.34, height: size * 0.34, borderRadius: "50%",
        background: "oklch(0.72 0.15 150)", color: "#fff", display: "flex",
        alignItems: "center", justifyContent: "center", fontSize: size * 0.18,
        fontWeight: 900, border: `2px solid ${bg}`,
      }}>$</span>
    </div>
  );
}

export function TopBar({ title, onBack, right }) {
  return (
    <div className="top-bar">
      {onBack && (
        <button type="button" onClick={onBack} aria-label="이전 화면" className="top-bar-back tap">‹</button>
      )}
      <div style={{ fontSize: 13, fontWeight: 700 }}>{title}</div>
      {right && <div style={{ marginLeft: "auto" }}>{right}</div>}
    </div>
  );
}

const RAIL = {
  ko: ["설정", "촬영", "프로필", "심사", "서류"],
  en: ["Setup", "Capture", "Profile", "Review", "Documents"],
};
export function Rail({ active, locale = "ko" }) {
  const labels = locale === "en" ? RAIL.en : RAIL.ko;
  return (
    <div style={{ padding: "2px 24px 12px", display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
      {labels.map((label, i) => (
        <div key={label} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6, flex: 1 }}>
          <div style={{ width: 10, height: 10, borderRadius: 99,
            background: i < active ? "var(--ok)" : i === active ? "var(--brand-2)" : "transparent",
            border: i > active ? "1.5px solid var(--line)" : "none" }} />
          <div style={{ fontSize: 9.5, fontWeight: i === active ? 700 : 500,
            color: i === active ? "oklch(0.5 0.1 45)" : i < active ? "oklch(0.4 0.012 60)" : "oklch(0.65 0.01 60)",
            fontFamily: "'Noto Sans KR',sans-serif", whiteSpace: "nowrap" }}>{label}</div>
        </div>
      ))}
    </div>
  );
}

export function PrimaryButton({ children, onClick, disabled }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} className={`primary-button${disabled ? "" : " tap"}`}
      style={{ minHeight: 56, display: "flex", alignItems: "center", justifyContent: "center",
        width: "100%", border: 0,
        borderRadius: 14, fontSize: 15.5, fontWeight: 700, transition: "transform .12s",
        background: disabled ? "oklch(0.86 0.01 60)" : "oklch(0.22 0.012 60)",
        color: disabled ? "oklch(0.55 0.01 60)" : "#fff" }}>
      {children}
    </button>
  );
}

// AI 쪽 doc_builder.CONF_THRESHOLD 와 같은 값이어야 한다. 어긋나면 서류에는
// 확인 주석이 붙는데 화면 배지는 뜨지 않는 구간이 생긴다.
const CONF_THRESHOLD = 0.95;

export function Field({ label, value, confidence, editable = false, dirty, error, onChange, locale = "ko" }) {
  const low = confidence != null && confidence < CONF_THRESHOLD;
  const en = locale === "en";
  return (
    <div style={{ padding: "13px 15px", borderRadius: 13, background: low ? "oklch(0.8 0.1 80 / 0.16)" : "#fff",
      border: error ? "1.5px solid #b64b3d" : low ? "1.5px solid var(--warn)" : "1px solid var(--line)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11.5, fontFamily: "'IBM Plex Mono',monospace", color: low ? "oklch(0.45 0.09 80)" : "var(--muted)" }}>{label}</span>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: low ? "oklch(0.5 0.14 80)" : "var(--ok)" }}>
          {error ? (en ? "Check required" : "확인 필요") : dirty ? (en ? "Edited" : "수정됨") : low ? (en ? "Check required" : "확인 필요") : !editable ? (en ? "Read only" : "수정 불가") : ""}
        </span>
      </div>
      <input className="profile-field-input" value={value ?? ""} disabled={!editable}
        onChange={editable ? (event) => onChange?.(event.target.value) : undefined} />
      {error && <div style={{ marginTop: 5, color: "#b64b3d", fontSize: 10.5 }}>{error}</div>}
    </div>
  );
}

// 서버가 내려준 question payload 하나를 그린다.
// input_type: text=자유입력, select=옵션 버튼, address=후보 선택만(자유 입력 금지).
export function QuestionCard({ payload, options, value, onChange, onSubmit, disabled, locale = "ko" }) {
  const { label, input_type: inputType, hint } = payload || {};
  const choice = inputType === "select" || inputType === "address";
  const en = locale === "en";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div>
        <b style={{ fontSize: 14.5, lineHeight: 1.45 }}>{label}</b>
        {hint && <div style={{ marginTop: 4, fontSize: 12, color: "var(--muted)", lineHeight: 1.45 }}>{hint}</div>}
      </div>

      {choice ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {options.map((option) => (
            <button key={option.value} type="button" disabled={disabled}
              onClick={() => onSubmit(option.value)} className="tap"
              style={{ minHeight: 44, padding: "0 14px", borderRadius: 11, fontSize: 13, fontWeight: 700,
                border: "1px solid var(--line)", background: "#fff", color: "oklch(0.25 0.012 60)" }}>
              {option.label}
            </button>
          ))}
          {options.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--muted)" }}>{en ? "No options are available." : "선택할 수 있는 항목을 받지 못했어요."}</div>
          )}
        </div>
      ) : (
        <form onSubmit={(event) => { event.preventDefault(); if (value.trim()) onSubmit(value.trim()); }}
          style={{ display: "flex", gap: 8 }}>
          <input className="profile-field-input" style={{ flex: 1 }} value={value} disabled={disabled}
            onChange={(event) => onChange(event.target.value)} placeholder={en ? "Enter your answer" : "답변을 입력하세요"} />
          <button type="submit" disabled={disabled || !value.trim()} className="tap"
            style={{ minHeight: 44, padding: "0 16px", borderRadius: 11, border: 0, fontSize: 13, fontWeight: 700,
              background: disabled || !value.trim() ? "oklch(0.86 0.01 60)" : "oklch(0.22 0.012 60)",
              color: disabled || !value.trim() ? "oklch(0.55 0.01 60)" : "#fff" }}>{en ? "Send" : "보내기"}</button>
        </form>
      )}
    </div>
  );
}

const TASK_UI = {
  locked:      { badge: "잠김",   cta: null,          tone: "oklch(0.65 0.01 60)" },
  available:   { badge: "시작 가능", cta: "시작하기",     tone: "var(--brand-2)" },
  in_progress: { badge: "진행 중",  cta: "계속하기",     tone: "oklch(0.6 0.13 45)" },
  done:        { badge: "완료",    cta: "결과 보기",    tone: "var(--ok)" },
};

// state.tasks 한 건. d_day 가 null 이면 배지를 숨긴다(기준일 미확보).
export function TaskCard({ task, busy, onStart, locale = "ko" }) {
  const en = locale === "en";
  const source = TASK_UI[task.status] || TASK_UI.locked;
  const labels = { locked: ["Locked", null], available: ["Available", "Start"], in_progress: ["In progress", "Continue"], done: ["Done", "View result"] };
  const meta = en ? { ...source, badge: labels[task.status]?.[0] || "Locked", cta: labels[task.status]?.[1] } : source;
  const locked = task.status === "locked";
  return (
    <div style={{ padding: "14px 15px", borderRadius: 13, background: locked ? "oklch(0.96 0.006 60)" : "#fff",
      border: "1px solid var(--line)", opacity: locked ? 0.75 : 1 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <b style={{ fontSize: 14, flex: 1 }}>{task.label}</b>
        {task.d_day != null && (
          <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 10.5, fontWeight: 700,
            padding: "3px 7px", borderRadius: 999, background: "oklch(0.8 0.1 80 / 0.2)", color: "oklch(0.45 0.09 80)" }}>
            D{task.d_day > 0 ? `-${task.d_day}` : `+${-task.d_day}`}
          </span>
        )}
        <span style={{ fontSize: 10.5, fontWeight: 700, color: meta.tone }}>{meta.badge}</span>
      </div>

      {locked && task.blocked_by?.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45 }}>
          {en ? "Complete first" : "먼저 완료해야 해요"} · {task.blocked_by.join(", ")}
        </div>
      )}
      {task.agency && <div style={{ marginTop: 6, fontSize: 11.5, color: "var(--muted)" }}>{en ? "Agency" : "제출처"} · {task.agency}</div>}
      {task.note && <div style={{ marginTop: 4, fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45 }}>{task.note}</div>}
      {task.required_docs?.length > 0 && (
        <div className="task-documents" aria-label={en ? "Required documents" : "준비물"}>
          <div className="task-documents-title"><span aria-hidden="true">📎</span>{en ? "What to bring" : "준비물"}</div>
          <ul>
            {task.required_docs.map((document) => <li key={document}>{document}</li>)}
          </ul>
        </div>
      )}

      {task.evidence?.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ fontSize: 11, color: "var(--muted)", cursor: "pointer" }}>{en ? "Legal basis" : "근거 법령"}</summary>
          {task.evidence.map((line) => (
            <div key={line} title={line} style={{ marginTop: 4, fontSize: 11, color: "var(--muted)", lineHeight: 1.45 }}>· {line}</div>
          ))}
        </details>
      )}

      {meta.cta && (
        <button type="button" disabled={busy} onClick={() => onStart(task)} className="tap"
          style={{ width: "100%", minHeight: 44, marginTop: 11, borderRadius: 11, border: 0, fontSize: 13, fontWeight: 700,
            background: busy ? "oklch(0.86 0.01 60)" : "oklch(0.22 0.012 60)", color: busy ? "oklch(0.55 0.01 60)" : "#fff" }}>
          {busy ? (en ? "Opening…" : "여는 중…") : meta.cta}
        </button>
      )}
    </div>
  );
}
