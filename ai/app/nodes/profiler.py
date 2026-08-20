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
    "gender":          {"ko": "성별",           "en": "Sex"},
    "passport_no":     {"ko": "여권번호",       "en": "Passport No."},
    "passport_issue":  {"ko": "여권 발급일",    "en": "Passport issue date"},
    "passport_expiry": {"ko": "여권 만료일",    "en": "Passport expiry"},
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


def public_profile(profile: dict) -> dict:
    """응답용 프로필 — 민감값 마스킹, 내부 필드 제외. 새 dict를 반환한다."""
    return {
        k: mask(k, v)
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
                "value": mask(k, v),
                "confidence": round(float(confidence.get(k, 1.0)), 2),
                "editable": k not in READONLY_FIELDS,
            }
            for k, v in profile.items()
            if k in LABELS and v is not None
        ],
    }


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