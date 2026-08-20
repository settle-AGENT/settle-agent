"""여권 OCR → profile 추출

시각영역(라벨+값)을 1차 소스로 쓰고, MRZ 는 교차검증에만 쓴다.
MRZ 는 문자 하나만 밀려도 필드 위치가 전부 어긋나므로 단독 소스로 쓰지 않는다.
"""
from __future__ import annotations

import re

from app.extractors.arc import (
    COUNTRY_CODE,
    OcrFailed,
    WrongDocument,
    call_clova,
    clean_texts,
    extract_texts,
)

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

    # 라벨은 나라마다 다르다 — "Passport No.", "Passport No./여권번호",
    # "여권번호" 등. 라벨과 값 사이에 / : 한글이 끼어도 잡는다.
    if m := re.search(r"(?:PASSPORT\s*NO|여권\s*번호)[.\s/:·]*([A-Z]{1,2}\d{6,8})",
                      blob):
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


# MRZ 1행은 P< + 발급국 3글자로 시작한다. 다른 서류에는 나오지 않는 모양이라
# "이것은 여권이다" 의 가장 단단한 근거다.
MRZ_ANCHOR = re.compile(r"^P[<K][A-Z]{3}")

# 후보 줄. 실물 OCR 은 44자를 못 채우는 일이 잦으므로 길이는 느슨하게 둔다.
_MRZ_SHAPE = re.compile(r"^[A-Z0-9<]{20,}$")


def find_mrz(texts: list[str]) -> list[str]:
    """MRZ 로 볼 줄들.

    앵커(P<XXX)가 있으면 그 문서는 여권이 확실하므로 나머지 후보 줄도 받는다 —
    2행은 OCR 이 꼬리의 < 채움을 잘라 먹는 일이 많아 그것까지 요구하면 교차검증이
    통째로 죽는다. 앵커가 없으면 < 를 요구한다. 그 문자가 없는 20자 대문자·숫자
    덩어리는 바코드나 일련번호일 뿐이다.
    """
    lines = [re.sub(r"\s+", "", t.upper()).replace("«", "<") for t in texts]
    cand = [s for s in lines if _MRZ_SHAPE.match(s)]
    if any(MRZ_ANCHOR.match(s) for s in cand):
        return cand
    return [s for s in cand if "<" in s]


# MRZ 1행: P<{발급국}{성}<<{이름}<<<…
# 성과 이름 사이는 << , 낱말 사이는 < , 남는 자리는 < 로 채운다.
_MRZ_NAME = re.compile(r"^P.([A-Z]{3})([A-Z<]+)$")


def name_from_mrz(mrz: list[str]) -> str | None:
    """MRZ 에서 영문 성명을 읽는다. 시각 영역은 글꼴 탓에 오인식이 잦아
    이름만큼은 MRZ 쪽이 안정적이다."""
    for line in mrz:
        m = _MRZ_NAME.match(line)
        if not m:
            continue
        surname, _, given = m.group(2).partition("<<")
        parts = [w for w in (surname + "<" + given).split("<") if w]
        if parts:
            return " ".join(parts)
    return None


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


# 여권 정보면의 칸 이름들. 계열로 묶는 이유 — "PASSPORT" 와 "PASSPORT NO" 는
# 포함 관계라 따로 세면 문자열 하나가 2점이 된다. 영수증에 "PASSPORT NO
# M1234567" 한 줄만 있어도 통과해 버렸다. 계열 단위로 세면 그건 2계열이다.
_FAMILIES = (
    ("PASSPORTNO", "여권번호"),                    # 번호 칸
    ("COUNTRYCODE", "발급국"),                     # 국가 코드
    ("DATEOFEXPIRY", "DATEOFISSUE", "기간만료일", "발급일"),
    ("DATEOFBIRTH", "NATIONALITY", "생년월일", "국적"),
    ("PASSPORT", "여권"),                          # 표제 — 가장 약하다
)
_SQUASH = re.compile(r"[\s\-.·,/]")
_MIN_FAMILIES = 3


# 표제는 낱말 단위로만 인정한다. blob 부분 문자열로 보면 "여권번호" 안의
# "여권" 이 표제로 잡혀, 통합신청서처럼 여권번호 칸이 있는 서류가 통과한다.
_TITLE_FAMILY = ("PASSPORT", "여권")


def signature_hits(texts: list[str]) -> list[str]:
    """발견된 칸 이름. 계열마다 첫 하나만 센다."""
    blob = _SQUASH.sub("", " ".join(texts)).upper()
    tokens = {_SQUASH.sub("", t).upper() for t in texts}
    found = []
    for family in _FAMILIES:
        haystack_is_token = family == _TITLE_FAMILY
        for word in family:
            w = _SQUASH.sub("", word).upper()
            if (w in tokens) if haystack_is_token else (w in blob):
                found.append(word)
                break
    return found


def looks_like_passport(texts: list[str]) -> bool:
    """MRZ 앵커 하나면 확실하다. 없으면 서로 다른 칸 세 계열을 요구한다.

    한둘로는 부족하다 — 통합신청서에도 "여권번호" 칸이 있고, 제출서류 안내문
    어디에도 "여권" 은 나온다. 정보면이라면 번호·국가·날짜·인적사항 칸이
    함께 보인다.
    """
    if any(MRZ_ANCHOR.match(s) for s in find_mrz(texts)):
        return True
    return len(signature_hits(texts)) >= _MIN_FAMILIES


def extract_profile(image_bytes: bytes, doc_type: str = "passport",
                    ext: str = "jpg", use_llm: bool = False) -> dict:
    texts = clean_texts(extract_texts(call_clova(image_bytes, ext)))
    blob = re.sub(r"\s+", " ", " ".join(texts)).upper()

    # 값을 뽑기 전에 서류부터 확인한다. 예전에는 "PASSPORT NO" 뒤에 번호처럼
    # 생긴 문자열만 있으면 무엇이든 통과했고, 반대로 라벨 표기가 조금만 달라도
    # 진짜 여권이 거부됐다. 통과 여부가 정규식 하나에 걸려 있었다.
    if not looks_like_passport(texts):
        raise WrongDocument(
            "여권 정보면으로 보이지 않습니다. 여권이 맞는지 확인하시고, "
            "사진과 정보가 있는 면 전체가 들어가게 다시 촬영해 주세요.")

    profile, confidence = parse_visual(blob)
    mrz = find_mrz(texts)

    # 시각 영역에서 번호를 못 읽었으면 MRZ 1행 뒤의 2행에서 앞 9자를 쓴다.
    if not profile.get("passport_no"):
        for line in mrz:
            if MRZ_ANCHOR.match(line):
                continue
            if m := re.match(r"^([A-Z0-9]{6,9})", line):
                profile["passport_no"] = m.group(1).rstrip("<")
                confidence["passport_no"] = 0.85
                break

    if not profile.get("passport_no"):
        raise OcrFailed("여권번호를 읽지 못했습니다. 정보면 전체가 들어가게 "
                        "다시 촬영해주세요.")

    if name := name_from_mrz(mrz):
        profile["name_en"] = name
        confidence["name_en"] = 0.93

    has_mrz, mismatched = cross_check(profile, mrz)
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