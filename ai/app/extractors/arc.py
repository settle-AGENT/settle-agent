"""외국인등록증 OCR → profile 추출

위치 가정: ai/app/extractors/arc.py
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

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "seed" / "ocr_cache"
CACHE_DIR = Path(os.getenv("OCR_CACHE_DIR", str(DEFAULT_CACHE_DIR)))
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
_ADDR_TAIL = re.compile(r"(\d|[로길가동읍면리호층번지])$")


def _trim_addr(addr: str) -> str:
    """뒤에 붙은 라벨·OCR 잡음을 잘라낸다."""
    for stop in _ADDR_STOP:
        addr = addr.split(stop)[0]
    toks = addr.split()
    # 주소 성분으로 끝나는 마지막 토큰까지만 남긴다
    for i in range(len(toks) - 1, -1, -1):
        if _ADDR_TAIL.search(toks[i]):
            return " ".join(toks[: i + 1])
    return " ".join(toks)    
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


# 외국인등록번호·국내거소신고번호의 성별코드는 5·6·7·8 이다.
# 주민등록번호는 1·2·3·4(1900년대) 또는 9·0(1800년대)를 쓴다.
# 형식(\d{6}-\d{7})은 둘이 같으므로 이 자리가 유일한 구분점이다.
_FOREIGN_SEX_CODES = {"5": ("19", "M"), "6": ("19", "F"),
                      "7": ("20", "M"), "8": ("20", "F")}


class WrongDocument(OcrFailed):
    """읽히긴 했으나 요구한 종류의 증명서가 아니다. 재촬영으로는 해결되지 않는다."""


def is_foreign_registration(arc: str | None) -> bool:
    """외국인등록번호 형태인가. 주민등록번호를 걸러내는 유일한 관문이다."""
    if not arc or not re.fullmatch(r"\d{6}-\d{7}", arc):
        return False
    return arc.split("-")[1][0] in _FOREIGN_SEX_CODES


def derive_from_arc(arc: str | None) -> dict:
    """등록번호에서 생년월일·성별을 계산한다."""
    if not is_foreign_registration(arc):
        return {}
    front, back = arc.split("-")
    century, gender = _FOREIGN_SEX_CODES[back[0]]
    return {
        "birth_date": f"{century}{front[0:2]}-{front[2:4]}-{front[4:6]}",
        # 키 이름은 gender 다. 나머지 코드가 전부 그 이름으로 읽는다 —
        # sex 로 넣으면 서식에도 안 실리고 여권 값과 대조도 되지 않는다.
        "gender": gender,
    }


# ──────────────────────────────────────────────── 서류 식별
# parse_rules 의 규칙은 전부 위치·문맥과 무관한 패턴 매칭이다. 텍스트가 많은
# 사진이면 영수증 번호가 등록번호로, 어딘가의 국가명이 국적으로, 대문자 두
# 낱말이 성명으로 걸린다. 값이 원문에 있는지 보는 verify() 로는 못 막는다 —
# 원문에서 뽑았으니 당연히 통과한다.
#
# 그래서 뽑기 전에 "이 서류가 등록증인가" 를 먼저 묻는다. 아래는 카드에 크게
# 인쇄돼 OCR 이 안정적으로 읽는 표제어들이고, 다른 서류에는 나오지 않는다.
_SIGNATURE = {
    "arc_front": ("외국인등록증", "외국인등록번호", "RESIDENCECARD",
                  "ALIENREGISTRATION", "REGISTRATIONNO"),
    "arc_back":  ("체류기간", "SOJOURN", "CHANGEOFRESIDENCE",
                  "일련번호", "SERIALNO", "안전칩", "발행국"),
}


def signature_hits(texts: list[str], doc_type: DocType) -> list[str]:
    """읽힌 텍스트에서 발견된 등록증 표제어."""
    blob = _squash(" ".join(texts))
    return [w for w in _SIGNATURE.get(doc_type, ()) if _squash(w) in blob]


def parse_rules(texts: list[str], doc_type: DocType) -> tuple[dict, dict]:
    """정규식 기반 1차 추출. LLM 없이 대부분 여기서 끝난다."""
    blob = re.sub(r"\s+", " ", " ".join(texts))
    p: dict = {}
    c: dict = {}

    # 등록번호는 앞뒷면 어디서 나오든 잡는다
    if m := _RE_ARC.search(blob):
        p["arc_no"] = f"{m.group(1)}-{m.group(2)}"
        c["arc_no"] = 0.97

    if doc_type == "arc_front":
        if m := _RE_ADDR.search(blob):
            addr = _trim_addr(re.sub(r"\s+", " ", m.group(1)).strip())
            if len(addr) >= 8:
                p["addr_kr"] = addr
                c["addr_kr"] = 0.93

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
                c["addr_kr"] = 0.93

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

    # 값을 뽑기 전에 서류부터 확인한다. 여기서 막지 않으면 무관한 사진의
    # 숫자·낱말이 그대로 프로필이 된다.
    if not signature_hits(texts, doc_type):
        side = "앞면" if doc_type == "arc_front" else "뒷면"
        raise WrongDocument(
            f"외국인등록증 {side}으로 보이지 않습니다. 등록증이 맞는지 "
            f"확인하시고, 카드 전체가 화면에 들어오도록 다시 촬영해 주세요.")

    profile, confidence = parse_rules(texts, doc_type)

    # 규칙으로 못 잡은 것만 LLM에 맡긴다
    want = [k for k in _TARGET.get(doc_type, []) if k not in profile]
    if use_llm and want:
        for k, v in structure_with_llm(texts, want).items():
            if k == "nationality":
                v = COUNTRY_CODE.get(str(v).upper(), v)
            profile[k] = v
            confidence[k] = 0.80        # LLM 유래는 낮게 → 사용자 확인 유도

    profile, dropped = verify(profile, texts)

    # 읽어낸 등록번호가 외국인등록번호가 아니면 다른 증명서다.
    # 여기서 막지 않으면 주민등록증이 그대로 프로필이 되고, 뒤에서
    # 여권 생년월일과 어긋나 보이지 않는 오류로 남는다.
    arc_no = profile.get("arc_no")
    if arc_no and not is_foreign_registration(arc_no):
        raise WrongDocument(
            "외국인등록증이 아닌 것 같습니다. 등록번호가 외국인등록번호 형식이 "
            "아닙니다. 외국인등록증을 촬영해 주세요.")

    if doc_type == "arc_front":
        derived = derive_from_arc(arc_no)
        profile.update(derived)
        if derived:
            confidence.setdefault("birth_date", confidence.get("arc_no", 0.9))

    if profile.get("addr_kr"):                    # LLM 폴백 경로도 한 번 거른다
        profile["addr_kr"] = _trim_addr(profile["addr_kr"])

    return {
        "profile": profile,
        "confidence": confidence,
        "dropped": dropped,
        "raw_texts": texts,
    }
