"""여권 OCR → profile 추출

시각영역(라벨+값)을 1차 소스로 쓰고, MRZ 는 교차검증에만 쓴다.
MRZ 는 문자 하나만 밀려도 필드 위치가 전부 어긋나므로 단독 소스로 쓰지 않는다.
"""
from __future__ import annotations

import re

from app.extractors.arc import (OcrFailed, COUNTRY_CODE, call_clova,
                                clean_texts, extract_texts)

_MON = {m: f"{i:02d}" for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

_D = r"(\d{1,2})\s+([A-Z]{3})\s+(\d{4})"


def _iso(m: re.Match) -> str | None:
    mon = _MON.get(m.group(2))
    return f"{m.group(3)}-{mon}-{int(m.group(1)):02d}" if mon else None


def parse_visual(blob: str) -> tuple[dict, dict]:
    p: dict = {}
    c: dict = {}

    if m := re.search(r"PASSPORT\s*NO\.?\s+([A-Z]{1,2}\d{6,8})", blob):
        p["passport_no"] = m.group(1)
        c["passport_no"] = 0.93

    if m := re.search(r"COUNTRY\s*CODE\s+([A-Z]{3})", blob):
        p["nationality"] = COUNTRY_CODE.get(m.group(1), m.group(1))
        c["nationality"] = 0.93

    for label, key in (("DATE\\s+OF\\s+BIRTH", "birth_date"),
                       ("DATE\\s+OF\\s+ISSUE", "passport_issue"),
                       ("DATE\\s+OF\\s+EXPIRY", "passport_expiry")):
        if m := re.search(label + r"\s+" + _D, blob):
            if v := _iso(m):
                p[key] = v
                c[key] = 0.93

    if m := re.search(r"\bSEX\s+([MF])\b", blob):
        p["gender"] = m.group(1)
        c["gender"] = 0.93

    return p, c


# ──────────────────────────────────────────── MRZ 교차검증
_WEIGHT = (7, 3, 1)


def _val(ch: str) -> int:
    return int(ch) if ch.isdigit() else (0 if ch == "<" else ord(ch) - 55)


def _check(s: str) -> int:
    return sum(_val(ch) * _WEIGHT[i % 3] for i, ch in enumerate(s)) % 10


def find_mrz(texts: list[str]) -> list[str]:
    out = []
    for t in texts:
        s = re.sub(r"\s+", "", t.upper()).replace("«", "<")
        if len(s) >= 20 and re.fullmatch(r"[A-Z0-9<]+", s):
            out.append(s)
    return out


def cross_check(profile: dict, mrz: list[str]) -> tuple[bool, list[str]]:
    """MRZ 에서 확인 가능한 것만 대조한다. 불일치는 신뢰도만 낮춘다."""
    if not mrz:
        return False, []

    blob = "".join(mrz)
    bad: list[str] = []

    if num := profile.get("passport_no"):
        if num in blob:
            head = blob[blob.index(num):blob.index(num) + 10]
            if len(head) == 10 and head[9].isdigit() \
                    and _check(num.ljust(9, "<")) != int(head[9]):
                bad.append("passport_no")
        else:
            bad.append("passport_no")

    if born := profile.get("birth_date"):
        if born[2:4] + born[5:7] + born[8:10] not in blob:
            bad.append("birth_date")

    if exp := profile.get("passport_expiry"):
        if exp[2:4] + exp[5:7] + exp[8:10] not in blob:
            bad.append("passport_expiry")

    return True, bad


def extract_profile(image_bytes: bytes, doc_type: str = "passport",
                    ext: str = "jpg", use_llm: bool = False) -> dict:
    texts = clean_texts(extract_texts(call_clova(image_bytes, ext)))
    blob = re.sub(r"\s+", " ", " ".join(texts)).upper()

    profile, confidence = parse_visual(blob)
    if not profile.get("passport_no"):
        raise OcrFailed("여권번호를 읽지 못했습니다. 정보면 전체가 들어가게 "
                        "다시 촬영해주세요.")

    has_mrz, mismatched = cross_check(profile, find_mrz(texts))
    for k in profile:
        if not has_mrz:
            confidence[k] = min(confidence.get(k, 0.9), 0.88)
        elif k in mismatched:
            confidence[k] = 0.70          # 사용자 확인 유도
        else:
            confidence[k] = 0.98          # 두 소스 일치

    return {
        "profile": profile,
        "confidence": confidence,
        "dropped": mismatched,
        "raw_texts": texts,
    }