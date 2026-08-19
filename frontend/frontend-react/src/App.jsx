import React, { useState } from "react";
import { BridgeMark, TopBar, Rail, PrimaryButton, Field } from "./components.jsx";
import {
  extractDocs, saveProfile, getVerdict, buildDocuments, nationalityLabel,
} from "./api.js";

const PURPOSES = ["등록금 납부", "아르바이트 급여", "본국 송금", "생활비", "장학금"];
const SCAN_PAGES = [
  { key: "arcFront", label: "외국인등록증 앞면", sub: "앞면" },
  { key: "arcBack", label: "외국인등록증 뒷면", sub: "뒷면" },
  { key: "passport", label: "여권", sub: "여권 사진면" },
];

const card = {
  padding: 15, borderRadius: 14, border: "1px solid var(--line)", background: "#fff",
};
const H2 = { margin: 0, fontSize: 25, lineHeight: 1.25, fontWeight: 800, letterSpacing: "-0.035em" };
const SUB = { margin: "7px 0 0", fontSize: 14, lineHeight: 1.5, color: "var(--muted)" };
const mono = { fontFamily: "'IBM Plex Mono',monospace" };

export default function App() {
  const [step, setStep] = useState(0);
  const [authMode, setAuthMode] = useState("login");
  const [auth, setAuth] = useState({ nickname: "", password: "", passwordConfirm: "", passcode: "" });
  const [authMessage, setAuthMessage] = useState("");
  const [lang, setLang] = useState("en");
  const [nat, setNat] = useState(null);

  const [scan, setScan] = useState(0);
  const [shots, setShots] = useState({});
  const [extract, setExtract] = useState(null);
  const [confirmed, setConfirmed] = useState({}); // 저신뢰 필드 확인 여부

  const [answers, setAnswers] = useState({ phone: null, cert: "yes", purposes: { 0: true, 2: true } });
  const [verdict, setVerdict] = useState(null);
  const [docs, setDocs] = useState(null);
  const [openDoc, setOpenDoc] = useState(null);

  const go = (n) => setStep(n);

  // ── 0 스플래시 ──
  if (step === 0)
    return (
      <Shell>
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
          <div style={{ width: "100%" }}><PrimaryButton onClick={() => { setAuthMode("login"); go(-1); }}>시작하기</PrimaryButton></div>
          <div onClick={() => docs ? go(8) : go(-1)} className="tap" style={{ width: "100%", minHeight: 50, display: "flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 14, border: "1px solid oklch(0.85 0.01 60)", background: "#fff", fontSize: 14, fontWeight: 700 }}>
            <span aria-hidden="true">🗂️</span> 내 서류함 열기 <span style={{ color: "var(--ok)", fontSize: 11 }}>3건 저장됨</span>
          </div>
        </div>
      </Shell>
    );

  // ── 인증 ──
  if (step === -1) {
    const signup = authMode === "signup";
    const passwordMatches = auth.password && auth.password === auth.passwordConfirm;
    const canSubmit = signup
      ? auth.nickname.trim().length >= 2 && auth.password.length >= 4 && passwordMatches
      : auth.nickname.trim().length >= 2 && auth.password.length >= 4 && /^\d{4}$/.test(auth.passcode);
    const updateAuth = (key) => (e) => setAuth((value) => ({ ...value, [key]: e.target.value }));
    const submitAuth = (e) => {
      e.preventDefault();
      if (!canSubmit) return;
      if (signup) {
        setAuthMode("login");
        setAuth((value) => ({ ...value, password: "", passwordConfirm: "", passcode: "" }));
        setAuthMessage("회원가입이 완료됐어요. 로그인해 주세요.");
        return;
      }
      setAuthMessage("");
      go(1);
    };
    return (
      <Shell>
        <TopBar title={signup ? "회원가입" : "로그인"} onBack={() => go(0)} />
        <div style={{ padding: "18px 26px 12px" }}>
          <BridgeMark size={56} />
          <h2 style={{ ...H2, marginTop: 20 }}>{signup ? "첫계좌를 시작해요" : "다시 만나서 반가워요"}</h2>
          <p style={SUB}>{signup ? "사용할 닉네임과 비밀번호를 입력해 주세요." : "닉네임과 비밀번호, 4자리 Passcode를 입력해 주세요."}</p>
        </div>
        <form onSubmit={submitAuth} className="scroll" style={{ padding: "12px 26px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
          {authMessage && <div role="status" style={{ padding: "11px 13px", borderRadius: 11, background: "oklch(.55 .14 150/.09)", color: "oklch(.42 .12 150)", fontSize: 12.5, lineHeight: 1.45 }}>{authMessage}</div>}
          <AuthInput label="닉네임" value={auth.nickname} onChange={updateAuth("nickname")} placeholder="닉네임을 입력하세요" autoComplete="username" />
          <AuthInput label="비밀번호" type="password" value={auth.password} onChange={updateAuth("password")} placeholder="비밀번호를 입력하세요" autoComplete={signup ? "new-password" : "current-password"} />
          {signup ? (
            <>
              <AuthInput label="비밀번호 확인" type="password" value={auth.passwordConfirm} onChange={updateAuth("passwordConfirm")} placeholder="비밀번호를 다시 입력하세요" autoComplete="new-password" />
              {auth.passwordConfirm && !passwordMatches && <div style={{ marginTop: -8, color: "#b64b3d", fontSize: 11.5 }}>비밀번호가 일치하지 않아요.</div>}
            </>
          ) : (
            <AuthInput label="Passcode" type="password" value={auth.passcode} onChange={(e) => setAuth((value) => ({ ...value, passcode: e.target.value.replace(/\D/g, "").slice(0, 4) }))} placeholder="4자리 숫자" inputMode="numeric" maxLength={4} autoComplete="one-time-code" />
          )}
        </form>
        <div style={{ padding: "12px 26px 34px" }}>
          <PrimaryButton disabled={!canSubmit} onClick={() => submitAuth({ preventDefault() {} })}>{signup ? "회원가입" : "로그인"}</PrimaryButton>
          <button type="button" onClick={() => { setAuthMode(signup ? "login" : "signup"); setAuthMessage(""); }}
            style={{ width: "100%", minHeight: 46, marginTop: 8, border: 0, background: "transparent", color: "var(--muted)", fontSize: 13 }}>
            {signup ? "이미 계정이 있나요? 로그인" : "계정이 없나요? 회원가입"}
          </button>
        </div>
      </Shell>
    );
  }

  // ── 1 언어 선택 ──
  if (step === 1)
    return (
      <Shell>
        <div style={{ paddingTop: 46 }}><Rail active={0} /></div>
        <div style={{ padding: "4px 26px 18px" }}>
          <h2 style={H2}>사용할 언어를 선택하세요</h2>
          <p style={SUB}>안내와 서류 설명에 사용할 언어예요. 나중에 다시 바꿀 수 있어요.</p>
        </div>
        <div className="scroll" style={{ padding: "0 26px 20px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <Pick on={lang === "ko"} onClick={() => setLang("ko")}><span style={{ width: "100%", textAlign: "left", padding: "0 4px" }}>한국어 <small style={{ float: "right", color: "var(--muted)", fontWeight: 500 }}>Korean</small></span></Pick>
            <Pick on={lang === "en"} onClick={() => setLang("en")}><span style={{ width: "100%", textAlign: "left", padding: "0 4px" }}>English <small style={{ float: "right", color: "var(--muted)", fontWeight: 500 }}>영어</small></span></Pick>
          </div>
        </div>
        <div style={{ padding: "8px 26px 34px" }}>
          <PrimaryButton onClick={() => go(2)}>계속</PrimaryButton>
        </div>
      </Shell>
    );

  // ── 2 촬영 ──
  if (step === 2) {
    const allShot = SCAN_PAGES.every((p) => shots[p.key]);
    const shoot = async () => {
      const next = { ...shots, [SCAN_PAGES[scan].key]: true };
      setShots(next);
      const empty = SCAN_PAGES.findIndex((p) => !next[p.key]);
      if (empty === -1) {
        const data = await extractDocs(next);
        setExtract(data);
        setNat(data?.profile?.nationality || null);
        go(3);
      } else setScan(empty);
    };
    return (
      <Shell>
        <TopBar title="서류 촬영" onBack={() => go(1)} />
        <Rail active={1} />
        <div style={{ padding: "4px 24px 12px" }}>
          <h2 style={H2}>3장을 촬영하세요</h2>
          <p style={SUB}>외국인등록증 앞면·뒷면, 여권 사진면. 카드를 눌러 전환하세요.</p>
        </div>
        <div style={{ padding: "0 24px 14px", display: "flex", gap: 8 }}>
          {SCAN_PAGES.map((p, i) => {
            const done = shots[p.key], active = scan === i;
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
          {shots[SCAN_PAGES[scan].key] && (
            <div style={{ width: 40, height: 40, borderRadius: 99, background: "var(--ok)", color: "#fff", fontSize: 20, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>✓</div>
          )}
          <div style={{ width: "92%", height: "72%", minHeight: 150, border: "1px dashed oklch(0.65 0.01 60)", borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", background: "repeating-linear-gradient(135deg,transparent 0 10px,oklch(.4 .01 60/.13) 10px 20px)" }}>
            <div style={{ ...mono, fontSize: 11, color: "oklch(0.7 0.01 60)", textAlign: "center" }}>{SCAN_PAGES[scan].label}</div>
          </div>
          <div style={{ alignSelf: "stretch", ...mono, fontSize: 10.5, color: "var(--ok)" }}>●&nbsp; 조명 상태 좋음</div>
        </div>
        <div style={{ margin: "12px 24px 0", padding: "10px 13px", borderRadius: 12, background: "oklch(.93 .008 60)", fontSize: 11.5, lineHeight: 1.5, color: "var(--muted)" }}>재학증명서는 사진 촬영 없이 종이 원본만 준비하면 돼요. 발급처는 뒤에서 안내해 드려요.</div>
        <div style={{ padding: "16px 24px 34px", display: "flex", gap: 12 }}>
          <div style={{ flex: 1 }}><PrimaryButton onClick={shoot}>{allShot ? "이 장 다시 찍기" : "촬영하기"}</PrimaryButton></div>
          <div className="tap" style={{ minHeight: 56, padding: "0 18px", display: "flex", alignItems: "center", borderRadius: 14, border: "1px solid oklch(0.85 0.01 60)", fontSize: 14, fontWeight: 600 }}>파일 첨부</div>
        </div>
      </Shell>
    );
  }

  // ── 3 프로필 만들기 (OCR 확인) ──
  if (step === 3) {
    const p = extract?.profile || {};
    const c = extract?.confidence || {};
    const lowKeys = Object.keys(c).filter((k) => c[k] < 0.9 && !confirmed[k]);
    const canGo = lowKeys.length === 0;
    const fieldRow = (key, label, value) => (
      <Field key={key} label={label} value={value}
        confidence={c[key]} confirmed={confirmed[key]} onFix={() => setConfirmed((s) => ({ ...s, [key]: true }))} />
    );
    return (
      <Shell>
        <TopBar title="프로필 만들기" onBack={() => go(2)} />
        <Rail active={2} />
        <div style={{ padding: "4px 24px 14px" }}>
          <h2 style={H2}>카드에서 만든 프로필</h2>
          <p style={SUB}>{canGo ? "모든 항목을 확인했어요. 계속 진행할 수 있어요." : `수정하려면 항목을 누르세요. ${lowKeys.length}개 항목을 확인해야 해요.`}</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 9 }}>
          <Label>외국인등록증에서</Label>
          {fieldRow("name_en", "이름", p.name_en)}
          <Row2>
            {fieldRow("visa_type", "체류자격", p.visa_type)}
            {fieldRow("arc_no", "등록번호", mask(p.arc_no))}
          </Row2>
          {fieldRow("addr_kr", "체류지 (뒷면)", p.addr_kr)}
          {fieldRow("stay_expiry", "체류기간", `2026.02.28 → ${p.stay_expiry}`)}
          <Label>여권에서</Label>
          <Row2>
            <Field label="여권번호" value="C41•••••" />
            <Field label="만료일" value="2031.04.09" />
          </Row2>
        </div>
        <div style={{ padding: "14px 24px 34px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45 }}>확인하기 전에는 진행되지 않아요. 읽지 못한 값은 임의로 채우지 않아요.</div>
          <PrimaryButton disabled={!canGo} onClick={async () => { await saveProfile(p, answers); go(4); }}>
            {canGo ? "확인하고 계속" : `확인 (${lowKeys.length}개 남음)`}
          </PrimaryButton>
        </div>
      </Shell>
    );
  }

  // ── 4 추가 질문 ──
  if (step === 4)
    return (
      <Shell>
        <TopBar title="몇 가지 질문" onBack={() => go(3)} />
        <Rail active={2} />
        <div style={{ padding: "4px 24px 12px" }}>
          <h2 style={H2}>두 가지만 더</h2>
          <p style={SUB}>서류에서 읽을 수 없는 항목이에요. 은행 창구에서 물어보는 것들이에요.</p>
        </div>
        <div className="scroll" style={{ padding: "6px 24px", display: "flex", flexDirection: "column", gap: 18 }}>
          <div>
            <QTitle>본인 명의 국내 휴대폰이 있나요?</QTitle>
            <div style={{ margin: "-7px 0 9px", fontSize: 11, color: "var(--muted)" }}>본인 명의 국내 통신사 개통 휴대폰</div>
            <Row2>
              <Pick ok on={answers.phone === "yes"} onClick={() => setAnswers({ ...answers, phone: "yes" })}>네, 있어요</Pick>
              <Pick on={answers.phone === "no"} onClick={() => setAnswers({ ...answers, phone: "no" })}>아직 없어요</Pick>
            </Row2>
            {answers.phone === "yes" && <Field label="휴대폰 번호" value="010-4•••-••21  영업 일치 확인됨" />}
          </div>
          <div>
            <QTitle>재학증명서 또는 입학허가서가 있나요?</QTitle>
            <Row2>
              <Pick ok on={answers.cert === "yes"} onClick={() => setAnswers({ ...answers, cert: "yes" })}>있어요</Pick>
              <Pick on={answers.cert === "no"} onClick={() => setAnswers({ ...answers, cert: "no" })}>아직 없어요</Pick>
            </Row2>
          </div>
          <div>
            <QTitle>계좌를 왜 만드나요?</QTitle>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {PURPOSES.map((label, i) => {
                const on = answers.purposes[i];
                return (
                  <div key={label} onClick={() => setAnswers({ ...answers, purposes: { ...answers.purposes, [i]: !on } })} className="tap"
                    style={{ minHeight: 44, display: "flex", alignItems: "center", padding: "0 15px", borderRadius: 999, fontSize: 13.5, fontWeight: on ? 700 : 600,
                      border: on ? "1.5px solid var(--brand-2)" : "1px solid oklch(0.88 0.01 60)", background: on ? "oklch(0.7 0.13 45 / 0.08)" : "#fff" }}>
                    {label}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <div style={{ padding: "14px 24px 34px" }}>
          <PrimaryButton disabled={!answers.phone} onClick={async () => {
            const scenario = new URLSearchParams(window.location.search).get("scenario");
            setVerdict(await getVerdict("mock", { ...answers, scenario }));
            go(5);
          }}>결과 보기</PrimaryButton>
        </div>
      </Shell>
    );

  // ── 5 판정 결과 ──
  if (step === 5 && verdict)
    return (
      <Shell>
        <div style={{ paddingTop: 46 }}><Rail active={3} /></div>
        <div style={{ padding: "8px 24px 20px", background: "oklch(0.22 0.012 60)", color: "#fff" }}>
          <div style={{ ...mono, fontSize: 11, letterSpacing: "0.12em", textTransform: "uppercase", color: verdict.blocker ? "oklch(0.8 0.1 80)" : "oklch(0.75 0.03 150)", marginBottom: 12 }}>계좌 개설 진단 결과</div>
          <h2 style={{ margin: 0, fontSize: 27, fontWeight: 800, lineHeight: 1.22, letterSpacing: "-0.02em" }}>{verdict.headline}</h2>
          <div style={{ marginTop: 10, fontSize: 12.5, lineHeight: 1.5, color: "oklch(.82 .012 60)" }}>{verdict.summary}</div>
        </div>
        <div className="scroll" style={{ padding: "18px 24px", display: "flex", flexDirection: "column", gap: 10 }}>
          {verdict.blocker && (
            <div style={{ ...card, border: "1.5px solid var(--warn)", background: "oklch(0.6 0.14 80 / 0.07)" }}>
              <RowBetween>
                <b style={{ fontSize: 15.5 }}>{verdict.blocker.title}</b>
                <span style={{ fontSize: 11.5, fontWeight: 700, color: "oklch(0.5 0.14 80)", whiteSpace: "nowrap" }}>{verdict.blocker.badge}</span>
              </RowBetween>
              {verdict.blocker.meta && <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 2 }}>{verdict.blocker.meta}</div>}
              <div style={{ fontSize: 13, lineHeight: 1.5, color: "oklch(0.38 0.012 60)", marginTop: 9 }}>{verdict.blocker.body}</div>
            </div>
          )}
          <div style={{ ...card, border: verdict.limited.ready ? "1.5px solid var(--ok)" : "1px solid var(--line)", background: verdict.limited.ready ? "oklch(0.55 0.14 150 / 0.06)" : "#fff" }}>
            <RowBetween>
              <b style={{ fontSize: 15.5 }}>한도제한계좌</b>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: verdict.limited.ready ? "oklch(0.45 0.12 150)" : "oklch(0.55 0.14 80)", whiteSpace: "nowrap" }}>{verdict.limited.status}</span>
            </RowBetween>
            <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 2 }}>1일 이체 100만원 한도</div>
            <div style={{ fontSize: 13, lineHeight: 1.5, color: "oklch(0.38 0.012 60)", marginTop: 9 }}>{verdict.limited.body}</div>
          </div>
          <div style={card}>
            <RowBetween>
              <b style={{ fontSize: 15.5 }}>일반계좌</b>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: "oklch(0.55 0.14 80)", whiteSpace: "nowrap" }}>{verdict.regular.status}</span>
            </RowBetween>
            <div style={{ fontSize: 13, lineHeight: 1.5, color: "oklch(0.38 0.012 60)", marginTop: 9 }}>{verdict.regular.body}</div>
          </div>
          <div style={{ padding: "14px 15px", borderRadius: 14, background: "oklch(0.93 0.008 60)" }}>
            <div style={{ ...mono, fontSize: 10.5, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 9 }}>판정 근거</div>
            {verdict.sources.map((s) => (
              <div key={s} style={{ fontSize: 12.5, lineHeight: 1.45, color: "oklch(0.35 0.012 60)", fontFamily: "'Noto Sans KR',sans-serif", marginBottom: 6 }}>· {s}</div>
            ))}
          </div>
        </div>
        <div style={{ padding: "14px 24px 34px", display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ fontSize: 11.5, lineHeight: 1.45, color: "var(--muted)" }}>이 판정은 은행 정책 기준의 사전 점검입니다. 최종 계좌 개설 여부는 은행이 결정합니다.</div>
          <div style={{ display: "flex", gap: 9 }}>
            <button type="button" onClick={() => go(4)} className="tap"
              style={{ width: 88, minHeight: 54, flex: "none", borderRadius: 13, border: "1px solid var(--line)", background: "#fff", color: "var(--ink)", fontSize: 13, fontWeight: 700 }}>
              답변 수정
            </button>
            <div style={{ minHeight: 54, flex: 1, borderRadius: 13, background: "#c44f40", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", padding: "0 10px", textAlign: "center", fontSize: 14, fontWeight: 800 }} onClick={() => go(6)} className="tap">{verdictCta(verdict.kind)}</div>
          </div>
        </div>
      </Shell>
    );

  // ── 6 준비 안내 ──
  if (step === 6 && verdict)
    return (
      <Shell>
        <TopBar title="준비할 것" onBack={() => go(5)} />
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
          <PrimaryButton onClick={async () => { setDocs(await buildDocuments("mock")); go(7); }}>내 서류함</PrimaryButton>
        </div>
      </Shell>
    );

  // ── 7 신청서 ──
  if (step === 7 && docs)
    return (
      <Shell>
        <TopBar title="내 신청서" onBack={() => go(6)} />
        <div style={{ padding: "4px 24px 16px" }}>
          <Rail active={4} />
          <h2 style={H2}>채워진 신청서 {docs.documents.length}종</h2>
          <p style={SUB}>인쇄하거나 창구에서 휴대폰으로 보여주세요.</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          {docs.documents.map((d) => (
            <div key={d.id} style={{ ...card, display: "flex", gap: 13 }}>
              <div style={{ width: 62, height: 84, flex: "none", borderRadius: 7, border: "1px solid oklch(0.88 0.01 60)", background: "repeating-linear-gradient(0deg, oklch(0.9 0.01 60) 0 3px, oklch(0.97 0.008 60) 3px 9px)" }} />
              <div style={{ flex: 1 }}>
                <b style={{ fontSize: 14.5 }}>{d.title}</b>
                <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "'Noto Sans KR',sans-serif" }}>{d.subtitle}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
                  <div style={{ flex: 1, height: 5, borderRadius: 99, background: "oklch(0.91 0.01 60)", overflow: "hidden" }}>
                    <div style={{ width: `${(d.filled / d.total) * 100}%`, height: "100%", background: d.filled === d.total ? "var(--ok)" : "var(--warn)" }} />
                  </div>
                  <div style={{ ...mono, fontSize: 11, fontWeight: 600, color: d.filled === d.total ? "oklch(0.45 0.12 150)" : "oklch(0.5 0.12 80)" }}>{d.filled}/{d.total}</div>
                </div>
                <div style={{ marginTop: 8, fontSize: 11, color: "var(--muted)", lineHeight: 1.4 }}>{d.filled === d.total ? "법에서 정한 필수 항목만 담아요. 임의로 추가하지 않아요." : "국가별 양식에만 있는 2개 항목: 본국 주소, 로마자 성명."}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ padding: "16px 24px 34px" }}>
          <PrimaryButton onClick={() => go(8)}>PDF로 저장</PrimaryButton>
          <div className="tap" style={{ marginTop: 10, minHeight: 50, border: "1px solid var(--line)", borderRadius: 13, display: "flex", alignItems: "center", justifyContent: "center", background: "#fff", fontSize: 13.5, fontWeight: 700 }}>PDF 미리보기</div>
        </div>
      </Shell>
    );

  // ── 8 보관함 ──
  if (step === 8 && docs)
    return (
      <Shell>
        <TopBar title="내 서류함" onBack={() => go(7)} right={<span style={{ fontSize: 12, color: "var(--muted)", display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 7, height: 7, borderRadius: 99, background: "var(--ok)" }} />저장됨</span>} />
        <div style={{ padding: "8px 24px 16px" }}>
          <h2 style={H2}>서류가 준비됐어요</h2>
          <p style={SUB}>파일을 누르면 PDF가 열려요. 모두 휴대폰에 저장되고 인터넷 없이도 열려요.</p>
        </div>
        <div className="scroll" style={{ padding: "0 24px", display: "flex", flexDirection: "column", gap: 10 }}>
          {[docs.documents[1], { id: "visit_summary", title: "은행 방문 요약", subtitle: "방문 요약 · 한국어", pages: 1, filled: 6, total: 6, expiresInDays: 6 }].map((d) => (
            <div key={d.id} onClick={() => { setOpenDoc(d); go(9); }} className="tap" style={{ ...card, display: "flex", gap: 13, alignItems: "center" }}>
              <div style={{ width: 44, height: 56, flex: "none", borderRadius: 7, border: "1px solid oklch(0.88 0.01 60)", background: "repeating-linear-gradient(0deg, oklch(0.9 0.01 60) 0 2px, oklch(0.97 0.008 60) 2px 7px)", display: "flex", alignItems: "flex-end", justifyContent: "center", paddingBottom: 5 }}>
                <span style={{ ...mono, fontSize: 8.5, fontWeight: 700, color: "var(--brand-2)" }}>PDF</span>
              </div>
              <div style={{ flex: 1 }}>
                <b style={{ fontSize: 14.5 }}>{d.title}</b>
                <div style={{ fontSize: 12, color: "var(--muted)", fontFamily: "'Noto Sans KR',sans-serif", marginTop: 1 }}>{d.subtitle}</div>
              </div>
              <span style={{ padding: "3px 8px", borderRadius: 999, fontSize: 10.5, fontWeight: 700, whiteSpace: "nowrap",
                background: d.expiresInDays <= 7 ? "oklch(0.6 0.14 80 / 0.14)" : "oklch(0.93 0.008 60)",
                color: d.expiresInDays <= 7 ? "oklch(0.45 0.12 80)" : "var(--muted)" }}>{d.expiresInDays}일 뒤 만료</span>
            </div>
          ))}
          <div style={{ borderTop: "1px solid var(--line)", marginTop: 6, paddingTop: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 8 }}>은행에 가져갈 것</div>
            {["외국인등록증 (앞·뒤)", "여권", "재학증명서", "본인 명의 휴대폰"].map((item) => <div key={item} style={{ padding: "10px 12px", marginBottom: 7, borderRadius: 10, background: "oklch(.965 .006 60)", fontSize: 12.5, fontWeight: 700 }}><span style={{ color: "var(--ok)", marginRight: 10 }}>✓</span>{item}</div>)}
            <div style={{ padding: "10px 12px", borderRadius: 10, background: "oklch(.965 .006 60)", fontSize: 12.5, color: "var(--muted)" }}>□　계좌개설신청서</div>
          </div>
        </div>
        <div style={{ padding: "16px 24px 34px" }}>
          <div style={{ fontSize: 11.5, lineHeight: 1.45, color: "var(--muted)", fontFamily: "'Noto Sans KR',sans-serif" }}>최종 계좌 개설 여부는 은행이 결정합니다. 본인확인과 서명은 창구에서 직접 진행합니다.</div>
        </div>
      </Shell>
    );

  // ── 9 PDF 뷰어 ──
  if (step === 9 && openDoc)
    return (
      <Shell dark>
        <TopBar title={openDoc.title} onBack={() => go(8)} />
        <div className="scroll" style={{ padding: "0 20px 20px" }}>
          <div style={{ background: "#fff", borderRadius: 6, padding: "22px 20px", fontFamily: "'Noto Sans KR',sans-serif" }}>
            <div style={{ borderBottom: "2px solid oklch(0.25 0.012 60)", paddingBottom: 10, marginBottom: 12 }}>
              <b style={{ fontSize: 16 }}>{openDoc.title}</b>
              <div style={{ ...mono, fontSize: 10, color: "var(--muted)", marginTop: 3 }}>{openDoc.filled}/{openDoc.total} FIELDS · {openDoc.pages}p</div>
            </div>
            {DOC_ROWS(extract?.profile, nat).map(([k, v]) => (
              <div key={k} style={{ display: "flex", gap: 10, padding: "8px 0", borderBottom: "1px solid oklch(0.92 0.01 60)" }}>
                <div style={{ width: 96, flex: "none", fontSize: 10.5, color: "var(--muted)" }}>{k}</div>
                <div style={{ flex: 1, fontSize: 12.5, fontWeight: 600 }}>{v}</div>
              </div>
            ))}
            <div style={{ marginTop: 18, display: "flex", justifyContent: "flex-end" }}>
              <div style={{ width: 110, textAlign: "center" }}>
                <div style={{ height: 26, borderBottom: "1px solid oklch(0.4 0.012 60)" }} />
                <div style={{ fontSize: 9.5, color: "var(--muted)", marginTop: 4 }}>신청인 서명</div>
              </div>
            </div>
          </div>
        </div>
        <div style={{ padding: "16px 20px 34px", display: "flex", gap: 9 }}>
          <FlatBtn>파일로 저장</FlatBtn>
          <FlatBtn brand>공유</FlatBtn>
        </div>
      </Shell>
    );

  return <Shell><div style={{ padding: 40 }}>로딩 중…</div></Shell>;
}

// ── 작은 헬퍼 컴포넌트 ──
function Shell({ children, dark }) {
  return (
    <div className="app-shell">
      <div className="phone" style={dark ? { background: "oklch(0.22 0.012 60)" } : undefined}>{children}</div>
    </div>
  );
}
function Label({ children }) {
  return <div style={{ padding: "6px 0", ...mono, fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--muted)" }}>{children}</div>;
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
function QTitle({ children }) {
  return <div style={{ fontSize: 14.5, fontWeight: 700, marginBottom: 10, fontFamily: "'Noto Sans KR',sans-serif" }}>{children}</div>;
}
function Row2({ children }) {
  return <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9, marginBottom: 10 }}>{children}</div>;
}
function RowBetween({ children }) {
  return <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10 }}>{children}</div>;
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
function FlatBtn({ children, brand }) {
  return <div className="tap" style={{ flex: 1, minHeight: 52, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 13, fontSize: 13.5, fontWeight: 700, color: "#fff", background: brand ? "var(--brand-2)" : "oklch(0.32 0.012 60)" }}>{children}</div>;
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
function DOC_ROWS(p = {}, nat) {
  return [
    ["성명 / Name", p.name_en || "—"],
    ["국적", nationalityLabel(nat)],
    ["생년월일", p.birth_date || "—"],
    ["외국인등록번호", mask(p.arc_no)],
    ["체류자격", `${p.visa_type || "—"} (유학)`],
    ["체류기간 만료", p.stay_expiry || "—"],
    ["국내 체류지", p.addr_kr || "—"],
    ["거래 목적", "등록금 납부, 본국 송금"],
    ["희망 계좌", "한도제한계좌 (입출금)"],
  ];
}
