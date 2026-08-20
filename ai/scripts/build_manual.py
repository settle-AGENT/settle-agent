"""외국인체류 안내매뉴얼 PDF → 체류자격별 코퍼스(JSON)

사용: uv run python scripts/build_manual.py corpus/manual rules/manual.json

법령이 아니라 '절차 안내'다. 조문이 없으니 (체류자격 × 쪽) 이 검색 단위다.
쪽 단위로 자르면 인용이 검증 가능해진다 — "안내매뉴얼 유학(D-2) p.42".

장(章) 경계 = 체류자격 경계다. 이걸 틀리면 D-2 유학생에게 E-9 규정을
물어다 주게 되므로, 자동 탐지 결과를 TOC 기준 개수로 검증한다.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

LAW = "외국인체류 안내매뉴얼"
LAW_FULL = "법무부 출입국·외국인정책본부 「외국인체류 안내매뉴얼」(2026. 8.)"
SOURCE_URL = "https://www.hikorea.go.kr"

MAX_CHARS = 900          # e5-small 은 512토큰에서 잘린다. 한글 기준 이 정도.
OVERLAP = 120            # 쪽 안에서 여러 조각이 날 때만 겹친다
MIN_CHARS = 200          # 이보다 짧은 쪽은 앞 조각에 붙인다

_PUA = re.compile(r"[\U000f0000-\U000fffff-]")
_PAGENO = re.compile(r"^\s*-\s*\d+\s*-\s*$")
_BANNER = re.compile(r"체류자격별\s*대상\s*및\s*제출서류")
_TOCLINK = re.compile(r"^[·\s]*목\s*차[·\s]*$")
# 본문 줄에 눌어붙은 "목차" 되돌아가기 링크. 이 문서에서 목차는 낱말로 쓰이지 않는다.
_TOCWORD = re.compile(r"(?<![가-힣])목\s*차(?![가-힣])")
# PDF 추출물에 섞여 나오는 제어문자. Postgres text 컬럼은 NUL 을 받지 않는다.
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# 장 제목 줄: "유     학(D-2)" / "비전문취업(E-9)"
_CHAPTER = re.compile(
    r"^ {0,14}([가-힣][가-힣A-Za-z0-9 ]{0,40}?) *\(([A-H]-\d+(?:-\d+)?(?:-[A-Z])?)\) *$")

# 제목이 세로쓰기로 그려져 텍스트 추출에 잡히지 않는 장.
# 쪽 번호를 박아두는 대신 keyword 로 검증한다 — 판이 바뀌면 조용히 틀리는 대신 경고한다.
_UNDETECTED: list[tuple[int, str, str | None, str]] = [
    # (시작쪽, 표시명, 대표코드, 그 쪽에 반드시 있어야 하는 말)
    (175, "회화지도", "E-2", "회화지도"),
    (186, "연구", "E-3", "고급과학기술인력"),
    (572, "지역특화형비자", "F-2-R", "지역특화형"),
    (658, "국내 성장 기반 외국인 청소년 취업·정주", "E-7-Y", "국내 성장 기반"),
    (672, "톱티어(Top-Tier) 비자", "E-7-T", "톱티어"),
    (714, "광역형 비자", "F-2-L", "광역형"),
    (778, "K-STAR 비자트랙", "E-7-S", "K-STAR"),
]

# 한 장이 여러 자격을 함께 다루는 경우 — 자격 필터가 놓치지 않게 넓혀준다
_EXTRA_VISAS = {
    "F-4": ["C-3-8", "F-1", "H-2", "F-4", "F-5"],          # 36. 외국국적동포 관련
    "F-2-R": ["F-2-R", "F-4-R", "E-7-R", "D-2-R"],         # 37. 지역특화형
    "E-7-T": ["D-10-T", "E-7-T", "F-2-T", "F-5-T"],        # 39. 톱티어
}

FRONT_START, FRONT_END = 3, 14        # 유의사항 · 공통사항 (자격 무관)

# 좌측 열 표제어. 쪽 전체에서 세어 가장 많이 나온 것을 그 쪽의 주제로 삼는다.
_TOPICS: list[tuple[str, re.Pattern[str]]] = [
    ("시간제취업", re.compile("시간제취업")),
    ("체류자격외 활동", re.compile("체류자격외활동|자격외활동")),
    ("근무처 변경·추가", re.compile("근무처의?변경[·․]?추가|근무처변경")),
    ("체류자격 변경허가", re.compile("체류자격변경허가|자격변경허가")),
    ("체류기간 연장허가", re.compile("체류기간연장허가|연장허가")),
    ("체류자격 부여", re.compile("체류자격부여")),
    ("재입국허가", re.compile("재입국허가")),
    ("체류지 변경신고", re.compile("체류지변경신고|체류지변경")),
    ("외국인등록", re.compile("외국인등록")),
    ("사증발급", re.compile("사증발급인정서|사증발급")),
    ("자격 해당자 및 활동범위", re.compile("자격해당자|활동범위")),
]
_MIN_TOPIC_HITS = 2


@dataclass
class Chapter:
    start: int                                    # 1-based, 포함
    end: int                                      # 1-based, 제외
    name: str
    code: str | None
    visas: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.name}({self.code})" if self.code else self.name


# ────────────────────────────────────────────── 텍스트
def read_pages(pdf: Path) -> list[str]:
    """layout 모드로 읽는다 — 표의 좌측 표제 열이 본문과 섞이지 않는다."""
    reader = PdfReader(str(pdf))
    out = []
    for page in reader.pages:
        raw = page.extract_text(extraction_mode="layout") or ""
        out.append(_PUA.sub(" ", unicodedata.normalize("NFC", raw)).replace("\xad", "-"))
    return out


def page_text(raw: str) -> str:
    """머리글·쪽번호·목차 링크를 걷어내고 공백을 접는다."""
    keep = [l.strip() for l in raw.splitlines()
            if l.strip() and not _PAGENO.match(l)
            and not _BANNER.search(l) and not _TOCLINK.match(l.strip())]
    joined = _TOCWORD.sub(" ", _CTRL.sub(" ", " ".join(keep)))
    return re.sub(r"\s+", " ", joined).strip()


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


# ────────────────────────────────────────────── 장 경계
def find_chapters(pages: list[str]) -> list[Chapter]:
    found: list[Chapter] = []
    for i, raw in enumerate(pages):
        if i + 1 < FRONT_END:
            continue
        head = [l.rstrip() for l in raw.splitlines() if l.strip()][:4]
        for line in head:
            m = _CHAPTER.match(line)
            if not m:
                continue
            name = _squash(m.group(1))
            if 1 <= len(name) <= 10:
                found.append(Chapter(i + 1, 0, name, m.group(2)))
            break

    for start, name, code, keyword in _UNDETECTED:
        if _squash(keyword) not in _squash(pages[start - 1]):
            print(f"  ! p{start} 에서 '{keyword}' 를 찾지 못했습니다 — "
                  f"매뉴얼 판이 바뀌었는지 확인하세요. '{name}' 장은 건너뜁니다.")
            continue
        found.append(Chapter(start, 0, name, code))

    found.sort(key=lambda c: c.start)
    for a, b in zip(found, found[1:]):
        a.end = b.start
    if found:
        found[-1].end = len(pages) + 1

    for c in found:
        c.visas = _EXTRA_VISAS.get(c.code or "", [c.code] if c.code else [])

    return [Chapter(FRONT_START, FRONT_END, "공통사항", None, [])] + found


# ────────────────────────────────────────────── 조각내기
def topic_of(text: str) -> str | None:
    flat = _squash(text)
    best, hits = None, _MIN_TOPIC_HITS - 1
    for label, pat in _TOPICS:
        n = len(pat.findall(flat))
        if n > hits:
            best, hits = label, n
    return best


def split(text: str) -> list[str]:
    """불릿·문장 경계에서 자른다. 겹침을 둬 경계에 걸린 문장을 잃지 않는다."""
    if len(text) <= MAX_CHARS:
        return [text]
    parts, buf = [], ""
    for piece in re.split(r"(?<=[.。])\s+|(?=\s[❍◦※▣‣•□❑▪])|(?=\s\d+\.\s)", text):
        piece = piece.strip()
        if not piece:
            continue
        if buf and len(buf) + len(piece) + 1 > MAX_CHARS:
            parts.append(buf)
            buf = (buf[-OVERLAP:] + " " + piece).strip()
        else:
            buf = f"{buf} {piece}".strip()
    if buf:
        parts.append(buf)
    return [p for p in parts if len(p) > 40]


def chapter_chunks(ch: Chapter, pages: list[str]) -> list[dict]:
    slug = ch.code or re.sub(r"[^가-힣A-Za-z0-9]", "", ch.name)[:20]
    out: list[dict] = []
    carry = ""                    # 너무 짧아 앞에 붙일 쪽
    carry_from = 0

    for p in range(ch.start, ch.end):
        text = page_text(pages[p - 1])
        if len(text) < 60:                       # 서식·빈 쪽
            continue
        if carry:
            text, first = f"{carry} {text}", carry_from
            carry = ""
        else:
            first = p
        if len(text) < MIN_CHARS:
            carry, carry_from = text, first
            continue
        out.extend(_emit(ch, slug, text, first, p))

    if carry:
        out.extend(_emit(ch, slug, carry, carry_from, carry_from))
    return out


def _emit(ch: Chapter, slug: str, text: str, first: int, last: int) -> list[dict]:
    pages_label = f"p.{first}" if first == last else f"p.{first}-{last}"
    topic = topic_of(text)
    heading = f"{ch.label} {topic}" if topic else ch.label
    parts = split(text)
    out = []
    for n, body in enumerate(parts, 1):
        suffix = f"-{n}" if len(parts) > 1 else ""
        out.append({
            "id": f"manual-{slug}-p{first}{suffix}",
            "doc_type": "manual",
            "law": LAW,
            "law_full": LAW_FULL,
            "article": ch.label,
            "heading": heading,
            "cite": f"{LAW} {ch.label} {pages_label}",
            "text": body,
            "visa": ch.visas,
            "page": first,
            "page_end": last,
        })
    return out


# ────────────────────────────────────────────── main
def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "corpus/manual")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "rules/manual.json")

    pdfs = sorted(src.glob("*.pdf")) if src.is_dir() else [src]
    if not pdfs:
        sys.exit(f"{src} 에 PDF 가 없습니다.")

    docs: list[dict] = []
    for pdf in pdfs:
        print(f"{pdf.name} 읽는 중…")
        pages = read_pages(pdf)
        chapters = find_chapters(pages)
        print(f"  {len(pages)}쪽, {len(chapters)}개 장")
        for ch in chapters:
            chunks = chapter_chunks(ch, pages)
            docs.extend(chunks)
            print(f"    {ch.label:34s} p{ch.start:>3}-{ch.end - 1:<3} {len(chunks):4d}조각")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n총 {len(docs)}조각 → {out}")


if __name__ == "__main__":
    main()
