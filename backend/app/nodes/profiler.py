"""신분증 이미지 → state.profile 갱신 + 확인 화면 payload 생성

마스킹 규칙:
  - mask()는 **응답을 만들 때만** 적용된다. state 원본은 항상 평문.
  - 서류(PDF)는 서버 내부에서 원본 평문으로 렌더된다.
"""
import re

from app.extractors import arc as arc_ex
from app.extractors import passport as pp_ex

LABELS = {
    "arc_no":      "Registration No.",
    "name_en":     "Full name",
    "nationality": "Nationality",
    "birth_date":  "Date of birth",
    "visa_type":   "Visa status",
    "stay_expiry": "Stay expiry",
    "addr_kr":     "Address",
    "entry_date":  "Date of entry",
    "org_name":    "School / Organization",
    "phone_kr":    "Phone (KR)",
    "purpose":     "Purpose",
    "gender":          "Sex",
    "passport_no":     "Passport No.",
    "passport_issue":  "Passport issue date",
    "passport_expiry": "Passport expiry",
}

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


def profile_to_payload(profile: dict, confidence: dict, doc_type: str) -> dict:
    """ui.type = profile_confirm 의 payload"""
    return {
        "doc_type": doc_type,
        "fields": [
            {
                "key": k,
                "label": LABELS[k],
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