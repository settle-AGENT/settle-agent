"""외국인등록증 OCR → profile 추출

위치 가정: backend/app/extractors/arc.py
반환 규약:
  - 값을 못 읽은 필드는 **키 자체를 넣지 않는다** (None을 넣으면 슬롯 필링이 오작동)
  - confidence는 필드별로 함께 반환 (< 0.9 이면 사용자 확인 대상)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Literal

import requests

CLOVA_INVOKE_URL = os.getenv("CLOVA_INVOKE_URL")
CLOVA_SECRET_KEY = os.getenv("CLOVA_SECRET_KEY")

CACHE_DIR = Path(__file__).resolve().parents[3] / "seed" / "ocr_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DocType = Literal["arc_front", "arc_back"]


class OcrFailed(RuntimeError):
    """OCR 자체가 실패. 재촬영을 요청해야 한다."""


# ──────────────────────────────────────────────── CLOVA 호출
def call_clova(image_bytes: bytes, ext: str = "jpg") -> dict:
    """CLOVA General OCR 호출. 동일 이미지는 캐시에서 반환."""
    key = hashlib.md5(image_bytes).hexdigest()
    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    if not CLOVA_INVOKE_URL or not CLOVA_SECRET_KEY:
        raise RuntimeError("CLOVA_INVOKE_URL / CLOVA_SECRET_KEY 환경변수가 없습니다")

    payload = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{
            "format": ext.lower().lstrip("."),
            "name": "arc",
            "data": base64.b64encode(image_bytes).decode(),
        }],
    }
    res = requests.post(
        CLOVA_INVOKE_URL,
        headers={"X-OCR-SECRET": CLOVA_SECRET_KEY},
        json=payload,
        timeout=30,
    )
    res.raise_for_status()
    result = res.json()
    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return result


def extract_texts(clova_response: dict) -> list[str]:
    """CLOVA 응답에서 인식된 텍스트 조각만 뽑는다."""
    images = clova_response.get("images", [])
    if not images:
        raise OcrFailed("CLOVA 응답에 images가 없습니다")

    texts: list[str] = []
    for image in images:
        if image.get("inferResult") != "SUCCESS":
            raise OcrFailed(f"OCR 실패: {image.get('message', 'unknown')}")
        for field in image.get("fields", []):
            if t := field.get("inferText", "").strip():
                texts.append(t)

    if not texts:
        raise OcrFailed("인식된 텍스트가 없습니다. 재촬영이 필요합니다")
    return texts


# ──────────────────────────────────────────────── 노이즈 제거
# 견본 이미지 워터마크 전용. 실물 카드에는 없으므로 없어도 무방하다.
_WM_PARTS = {"SAMPLE", "SAMPL", "AMPLE", "SAMP", "MPLE", "AMPL", "SAM", "MPL", "PLE"}
_WM_KO = {"샘플", "견본"}


def clean_texts(texts: list[str]) -> list[str]:
    out = []
    for t in texts:
        s = t.strip()
        if not s or s in _WM_KO:
            continue
        if s.upper() in _WM_PARTS:      # 완전 일치만 제거 (부분 문자열 매칭 금지)
            continue
        out.append(s)
    return out


# ──────────────────────────────────────────────── 규칙 추출
_RE_ARC = re.compile(r"(\d{6})\s*[-–—]\s*(\d{7})")
_RE_VISA = re.compile(r"\(\s*([A-Z])\s*[-–—]\s*(\d{1,2})\s*\)")
_RE_DATE = re.compile(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})")
_RE_ADDR = re.compile(
    r"([가-힣]+(?:특별자치시|특별자치도|특별시|광역시|도)\s+[가-힣0-9\s\-]{4,60})")
# 주소 뒤에 붙어 들어오는 라벨 — 여기서 잘라낸다
_ADDR_STOP = ("발행국", "일련번호", "신고일자", "체류지", "발급일자", "체류자격",
              "안전칩", "발급", "서울출입국", "출입국")
_RE_NAME = re.compile(r"\b[A-Z]{2,}(?:\s+[A-Z]+)+\b")

_LABEL_WORDS = {
    "KOR", "RESIDENCE", "CARD", "PHOTO", "CHIEF", "SEOUL", "IMMIGRATION",
    "OFFICE", "NAME", "STATUS", "ADDRESS", "COUNTRY", "REGION", "PERMISSION",
    "EXPIRY", "ISSUE", "DATE", "REGISTRATION", "REGISTRATIONNO", "NO",
    "SOJOURN", "PERIOD", "UNTIL", "CHANGE", "OF", "SERIAL", "IC", "CHIP",
}

COUNTRY_CODE = {
    "VIETNAM": "VNM", "VIET NAM": "VNM", "CHINA": "CHN", "UZBEKISTAN": "UZB",
    "NEPAL": "NPL", "MONGOLIA": "MNG", "PHILIPPINES": "PHL", "INDONESIA": "IDN",
    "THAILAND": "THA", "CAMBODIA": "KHM", "MYANMAR": "MMR", "JAPAN": "JPN",
    "RUSSIA": "RUS", "KAZAKHSTAN": "KAZ", "SRI LANKA": "LKA", "INDIA": "IND",
    "BANGLADESH": "BGD", "PAKISTAN": "PAK", "UNITED STATES": "USA",
}


def _fmt_date(m: re.Match) -> str:
    y, mo, d = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"


def derive_from_arc(arc: str | None) -> dict:
    """등록번호에서 생년월일·성별을 계산한다."""
    if not arc or not re.fullmatch(r"\d{6}-\d{7}", arc):
        return {}
    front, back = arc.split("-")
    code = back[0]
    century = {"5": "19", "6": "19", "7": "20", "8": "20"}.get(code)
    gender = {"5": "M", "6": "F", "7": "M", "8": "F"}.get(code)
    if not century:
        return {}
    return {
        "birth_date": f"{century}{front[0:2]}-{front[2:4]}-{front[4:6]}",
        "sex": gender,
    }


def parse_rules(texts: list[str], doc_type: DocType) -> tuple[dict, dict]:
    """정규식 기반 1차 추출. LLM 없이 대부분 여기서 끝난다."""
    blob = re.sub(r"\s+", " ", " ".join(texts))
    p: dict = {}
    c: dict = {}

    if doc_type == "arc_front":
        if m := _RE_ARC.search(blob):
            p["arc_no"] = f"{m.group(1)}-{m.group(2)}"
            c["arc_no"] = 0.97

        for token in sorted(COUNTRY_CODE, key=len, reverse=True):
            if token in blob.upper():
                p["nationality"] = COUNTRY_CODE[token]
                c["nationality"] = 0.96
                break

        for m in _RE_NAME.finditer(blob):
            cand = m.group(0).strip()
            words = cand.split()
            if any(w.upper() in _LABEL_WORDS for w in words):
                continue
            if cand.upper() in COUNTRY_CODE:
                continue
            if len(words) >= 2:
                p["name_en"] = cand
                c["name_en"] = 0.93
                break

    else:  # arc_back
        if m := _RE_VISA.search(blob):
            p["visa_type"] = f"{m.group(1)}-{m.group(2)}"
            c["visa_type"] = 0.95

        dates = sorted({_fmt_date(m) for m in _RE_DATE.finditer(blob)})
        if dates:
            p["stay_expiry"] = dates[-1]      # 가장 늦은 날짜 = 만료일
            c["stay_expiry"] = 0.92

        if m := _RE_ADDR.search(blob):
            addr = re.sub(r"\s+", " ", m.group(1)).strip()
            for stop in _ADDR_STOP:                 # 뒤에 붙은 라벨 잘라내기
                addr = addr.split(stop)[0].strip()
            if len(addr) >= 8:
                p["addr_kr"] = addr
                c["addr_kr"] = 0.88

    return p, c


# ──────────────────────────────────────────────── LLM 폴백 (부족분만)
_PROMPT = """아래는 외국인등록증을 OCR로 읽은 텍스트 조각들이다.
라벨과 값의 순서가 뒤섞여 있을 수 있다.

{ocr_text}

다음 키의 값만 JSON으로 출력하라. 설명·주석·백틱 금지.
찾을 수 없으면 null. 절대 추측하지 마라.

{schema}"""

_LLM_HINT = {
    "name_en": "영문 성명 (여권 표기)",
    "arc_no": "000000-0000000 형식",
    "nationality": "국적 영문 국가명",
    "visa_type": "D-2 같은 코드만",
    "stay_expiry": "체류기간 만료일 YYYY-MM-DD",
    "addr_kr": "체류지 주소",
}


def structure_with_llm(texts: list[str], want: list[str]) -> dict:
    if not want:
        return {}
    from app.tools.llm import generate  # 팀 공통 LLM 래퍼

    schema = json.dumps({k: _LLM_HINT[k] for k in want}, ensure_ascii=False, indent=2)
    raw = generate(_PROMPT.format(ocr_text="\n".join(texts), schema=schema))
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    return {k: v for k, v in data.items() if v}


# ──────────────────────────────────────────────── 검증
_FORMAT = {
    "arc_no": re.compile(r"\d{6}-\d{7}"),
    "visa_type": re.compile(r"[A-Z]-\d{1,2}"),
    "stay_expiry": re.compile(r"\d{4}-\d{2}-\d{2}"),
    "birth_date": re.compile(r"\d{4}-\d{2}-\d{2}"),
}
# OCR 원문 대조가 의미 있는 필드 (날짜·코드는 정규화되므로 제외)
_GROUNDED = ["name_en", "addr_kr"]


def _squash(s: str) -> str:
    return re.sub(r"[\s\-.·,]", "", s).upper()


def verify(profile: dict, texts: list[str]) -> tuple[dict, list[str]]:
    """LLM이 지어낸 값과 형식 위반을 걸러낸다."""
    source = _squash(" ".join(texts))
    dropped: list[str] = []

    for key in _GROUNDED:
        v = profile.get(key)
        if v and _squash(str(v)) not in source:      # 대소문자·공백 무시 비교
            profile.pop(key)
            dropped.append(key)

    for key, pattern in _FORMAT.items():
        v = profile.get(key)
        if v and not pattern.fullmatch(str(v)):
            profile.pop(key)
            dropped.append(key)

    # 체류자격 유효집합 대조 — 여기서 걸리면 OCR 오인식이다
    from app.rules.loader import VALID_VISA_CODES  # visa_codes.yaml
    v = profile.get("visa_type")
    if v and v not in VALID_VISA_CODES:
        profile.pop("visa_type")
        dropped.append("visa_type")

    return profile, dropped


# ──────────────────────────────────────────────── 진입점
_TARGET = {
    "arc_front": ["name_en", "arc_no", "nationality"],
    "arc_back": ["visa_type", "stay_expiry", "addr_kr"],
}


def extract_profile(image_bytes: bytes, doc_type: DocType,
                    ext: str = "jpg", use_llm: bool = True) -> dict:
    """등록증 이미지 → profile 조각

    반환:
        profile     읽어낸 필드만 (못 읽은 키는 없음)
        confidence  필드별 신뢰도
        dropped     검증에서 버려진 필드
        raw_texts   OCR 원문 (디버깅·감사용)
    """
    texts = clean_texts(extract_texts(call_clova(image_bytes, ext)))

    profile, confidence = parse_rules(texts, doc_type)

    # 규칙으로 못 잡은 것만 LLM에 맡긴다
    want = [k for k in _TARGET[doc_type] if k not in profile]
    if use_llm and want:
        for k, v in structure_with_llm(texts, want).items():
            if k == "nationality":
                v = COUNTRY_CODE.get(str(v).upper(), v)
            profile[k] = v
            confidence[k] = 0.80        # LLM 유래는 낮게 → 사용자 확인 유도

    profile, dropped = verify(profile, texts)

    if doc_type == "arc_front":
        profile.update(derive_from_arc(profile.get("arc_no")))
        confidence.setdefault("birth_date", confidence.get("arc_no", 0.9))

    return {
        "profile": profile,
        "confidence": confidence,
        "dropped": dropped,
        "raw_texts": texts,
    }