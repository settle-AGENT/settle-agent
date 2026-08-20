"""신분증 이미지 → state.profile 갱신 + 확인 화면 payload 생성

마스킹 규칙:
  - mask()는 **응답을 만들 때만** 적용된다. state 원본은 항상 평문.
  - 서류(PDF)는 서버 내부에서 원본 평문으로 렌더된다.
"""
import re

from app.extractors import arc as arc_ex
from app.extractors import passport as pp_ex

# 화면에 나가는 라벨. 닫힌 집합이라 LLM 번역을 태우지 않는다 —
# llm.translate 에는 캐시가 없어 응답마다 API 호출이 붙는다.
LABELS = {
    "arc_no":      {"ko": "외국인등록번호",   "en": "Registration No."},
    "name_en":     {"ko": "성명",             "en": "Full name"},
    "nationality": {"ko": "국적",             "en": "Nationality"},
    "birth_date":  {"ko": "생년월일",         "en": "Date of birth"},
    "visa_type":   {"ko": "체류자격",         "en": "Visa status"},
    "stay_expiry": {"ko": "체류기간 만료일",  "en": "Stay expiry"},
    "addr_kr":     {"ko": "체류지",           "en": "Address"},
    "entry_date":  {"ko": "입국일",           "en": "Date of entry"},
    "org_name":    {"ko": "소속 학교·기관",   "en": "School / Organization"},
    "phone_kr":    {"ko": "휴대전화",         "en": "Phone (KR)"},
    "purpose":     {"ko": "사용 목적",        "en": "Purpose"},
    "income_source": {"ko": "자금 출처",      "en": "Source of funds"},
    "gender":          {"ko": "성별",           "en": "Sex"},
    "passport_no":     {"ko": "여권번호",       "en": "Passport No."},
    "passport_issue":  {"ko": "여권 발급일",    "en": "Passport issue date"},
    "passport_expiry": {"ko": "여권 만료일",    "en": "Passport expiry"},
}

# 내부 상태와 서식 매핑은 안정적인 enum 값을 사용하지만, 이 값이 프로필
# 응답이나 LLM 문맥으로 새면 living_expense 같은 개발자용 문자열이 사용자에게
# 그대로 보인다. 사용자 경계에서는 이 닫힌 표를 통해서만 표시한다.
VALUE_LABELS = {
    "purpose": {
        "living_expense": {"ko": "생활비", "en": "Living expenses"},
        "tuition": {"ko": "학비", "en": "Tuition"},
        "salary": {"ko": "급여", "en": "Salary"},
        "remittance": {"ko": "송금", "en": "Remittance"},
    },
    "income_source": {
        "scholarship": {"ko": "장학금", "en": "Scholarship"},
        "family_support": {"ko": "가족 지원", "en": "Family support"},
        "part_time": {"ko": "아르바이트", "en": "Part-time job"},
        "savings": {"ko": "예금·저축", "en": "Savings"},
    },
}


def label_of(key: str, locale: str = "en") -> str:
    """LABELS 는 {ko, en} 이다. 모르는 locale 은 영어로 떨어뜨린다."""
    entry = LABELS.get(key)
    if not entry:
        return key
    return entry.get(locale) or entry["en"]

# 응답에 내보낼 때 마스킹할 필드
MASKED_FIELDS = {"arc_no"}

# 사용자가 화면에서 수정할 수 없는 필드 (마스킹되어 나가므로)
READONLY_FIELDS = {"arc_no"}

MASK_PATTERN = re.compile(r"\*{3,}")


def mask(key: str, value) -> str:
    """응답용 변환. 원본은 절대 바꾸지 않는다."""
    if key in MASKED_FIELDS and value:
        return f"{str(value)[:6]}-*******"
    return str(value)


def display_value(key: str, value, locale: str = "en") -> str:
    """사용자에게 보여 줄 필드 값. 내부 enum은 표시명으로, 민감값은 마스킹한다."""
    entry = VALUE_LABELS.get(key, {}).get(str(value))
    if entry:
        return entry.get(locale) or entry["en"]
    return mask(key, value)


def public_profile(profile: dict, locale: str = "en") -> dict:
    """응답용 프로필 — 민감값 마스킹, 내부 필드 제외. 새 dict를 반환한다."""
    return {
        k: display_value(k, v, locale)
        for k, v in profile.items()
        if k in LABELS and v is not None
    }


def profile_to_payload(profile: dict, confidence: dict, doc_type: str,
                       locale: str = "en") -> dict:
    """ui.type = profile_confirm 의 payload"""
    return {
        "doc_type": doc_type,
        "fields": [
            {
                "key": k,
                "label": label_of(k, locale),
                "value": display_value(k, v, locale),
                "confidence": round(float(confidence.get(k, 1.0)), 2),
                "editable": k not in READONLY_FIELDS,
            }
            for k, v in profile.items()
            if k in LABELS and v is not None
        ],
    }


# ──────────────────────────────────────────────────────────
# 서류 간 동일인 대조
# ──────────────────────────────────────────────────────────
# 프로필은 여러 장의 서류가 합쳐져 만들어진다. 병합은 나중 값이 이기므로
# 대조하지 않으면 다른 사람의 서류가 조용히 섞인다 — 등록증의 이름과
# 여권의 생년월일이 한 프로필에 담기고, 그대로 계좌개설 서식에 실린다.
#
# 이 세 가지는 표기 흔들림이 없다. 다르면 다른 사람이다.
HARD_KEYS = ("birth_date", "nationality", "gender")

# 이름은 로마자 표기가 서류마다 갈린다 (WANG XIAO LI / WANGXIAOLI).
# 다르다고 거부하면 오탐이 난다. 확인만 요청한다.
SOFT_KEYS = ("name_en",)

_NAME_STRIP = re.compile(r"[^A-Z0-9]")


def _comparable(key: str, value) -> str:
    v = str(value).strip().upper()
    return _NAME_STRIP.sub("", v) if key in SOFT_KEYS else v


def conflicts(existing: dict, incoming: dict, keys) -> dict[str, tuple[str, str]]:
    """양쪽에 다 있고 값이 다른 필드. {key: (기존, 새 값)}"""
    out: dict[str, tuple[str, str]] = {}
    for key in keys:
        old, new = existing.get(key), incoming.get(key)
        if old in (None, "") or new in (None, ""):
            continue
        if _comparable(key, old) != _comparable(key, new):
            out[key] = (str(old), str(new))
    return out


def apply_edits(state: dict, edits: dict) -> dict:
    """사용자가 확인 화면에서 고친 값을 반영.

    마스킹된 값(990101-*******)이 그대로 되돌아오면 무시한다.
    안 그러면 원본 평문이 마스크 문자열로 덮어써진다.
    """
    profile = state.setdefault("profile", {})
    for k, v in edits.items():
        if v is None or v == "":
            continue
        if MASK_PATTERN.search(str(v)):        # 마스킹된 값 → 원본 유지
            continue
        profile[k] = v
        state.setdefault("confidence", {})[k] = 1.0   # 사람이 확인함
    return state


def run(state: dict, image_bytes: bytes, doc_type: str, ext: str = "jpg") -> tuple[dict, dict]:
    """returns (state, ui_payload)"""
    mod = pp_ex if doc_type == "passport" else arc_ex
    r = mod.extract_profile(image_bytes, doc_type, ext=ext, use_llm=False)

    state.setdefault("profile", {}).update(r["profile"])     # 평문 저장
    state.setdefault("confidence", {}).update(r["confidence"])
    state["raw_texts"] = r["raw_texts"]        # Ledger용, 응답엔 미포함
    state["dropped"] = r["dropped"]

    return state, profile_to_payload(state["profile"], state["confidence"], doc_type)
