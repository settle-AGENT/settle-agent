"""법령 PDF → 조문 단위 코퍼스(JSON)

사용: uv run python scripts/build_corpus.py corpus rules/corpus.json
조문 하나가 검색 단위다. 답변은 이 안의 원문만 인용한다.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from pypdf import PdfReader

_ART = re.compile(r"^\s*(제\d+조(?:의\d+)?)\s*\(([^)]{1,40})\)")
_LAW = re.compile(r"^\s*(.+?)\s*\(\s*약칭:\s*(.+?)\s*\)")


def _pdf_text(p: Path) -> str:
    return "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)


def parse(path: Path) -> list[dict]:
    raw = unicodedata.normalize("NFC", _pdf_text(path))
    lines = [l.rstrip() for l in raw.splitlines()]

    title = short = path.stem
    for i, l in enumerate(lines[:40]):
        if l.strip().startswith("[시행"):
            for j in range(i - 1, -1, -1):          # 바로 위 비지 않은 줄 = 법령명
                cand = lines[j].strip()
                if not cand:
                    continue
                if m := _LAW.match(cand):
                    title, short = m.group(1).strip(), m.group(2).strip()
                else:
                    title = short = cand
                break
            break

    arts, cur = [], None
    for l in lines:
        if "국가법령정보센터" in l or "법제처" in l:
            continue
        if m := _ART.match(l):
            if cur:
                arts.append(cur)
            cur = {"article": m.group(1), "heading": m.group(2), "lines": [l.strip()]}
        elif cur is not None:
            cur["lines"].append(l.strip())
    if cur:
        arts.append(cur)

    out = []
    for a in arts:
        body = re.sub(r"\s{2,}", " ",
                      re.sub(r"\s*\n\s*", " ", "\n".join(a["lines"]))).strip()
        if len(body) < 15:
            continue
        out.append({
            "id": f"{short}-{a['article']}",
            "law": short, "law_full": title,
            "article": a["article"], "heading": a["heading"],
            "cite": f"{short} {a['article']}({a['heading']})",
            "text": body[:2200],
        })
    return out


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    docs: list[dict] = []
    for p in sorted(src.glob("*.pdf")):
        arts = parse(p)
        print(f"{p.name[:44]:46s} {len(arts):4d}개 조문")
        docs.extend(arts)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n총 {len(docs)}개 조문 → {out}")


if __name__ == "__main__":
    main()