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

export function TopBar({ title, onBack, right }) {
  return (
    <div style={{ padding: "48px 24px 12px", display: "flex", alignItems: "center", gap: 14 }}>
      {onBack && (
        <div onClick={onBack} className="tap" style={{ fontSize: 20, color: "var(--muted)", padding: "4px 8px 4px 0" }}>‹</div>
      )}
      <div style={{ fontSize: 13, fontWeight: 700 }}>{title}</div>
      {right && <div style={{ marginLeft: "auto" }}>{right}</div>}
    </div>
  );
}

const RAIL = ["설정", "촬영", "프로필", "심사", "서류"];
export function Rail({ active }) {
  return (
    <div style={{ padding: "2px 24px 12px", display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
      {RAIL.map((label, i) => (
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
    <div onClick={disabled ? undefined : onClick} className={disabled ? "" : "tap"}
      style={{ minHeight: 56, display: "flex", alignItems: "center", justifyContent: "center",
        borderRadius: 14, fontSize: 15.5, fontWeight: 700, transition: "transform .12s",
        background: disabled ? "oklch(0.86 0.01 60)" : "oklch(0.22 0.012 60)",
        color: disabled ? "oklch(0.55 0.01 60)" : "#fff" }}>
      {children}
    </div>
  );
}

export function Field({ label, value, confidence, editable = false, dirty, error, onChange }) {
  const low = confidence != null && confidence < 0.9;
  return (
    <div style={{ padding: "13px 15px", borderRadius: 13, background: low ? "oklch(0.8 0.1 80 / 0.16)" : "#fff",
      border: error ? "1.5px solid #b64b3d" : low ? "1.5px solid var(--warn)" : "1px solid var(--line)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11.5, fontFamily: "'IBM Plex Mono',monospace", color: low ? "oklch(0.45 0.09 80)" : "var(--muted)" }}>{label}</span>
        <span style={{ fontSize: 10.5, fontWeight: 700, color: low ? "oklch(0.5 0.14 80)" : "var(--ok)" }}>
          {error ? "확인 필요" : dirty ? "수정됨" : low ? "확인 필요" : confidence != null ? `${Math.round(confidence * 100)}%` : !editable ? "수정 불가" : ""}
        </span>
      </div>
      <input className="profile-field-input" value={value ?? ""} disabled={!editable}
        onChange={editable ? (event) => onChange?.(event.target.value) : undefined} />
      {error && <div style={{ marginTop: 5, color: "#b64b3d", fontSize: 10.5 }}>{error}</div>}
    </div>
  );
}
