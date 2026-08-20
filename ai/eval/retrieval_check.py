"""검색이 정상인지 확인한다.

사용: DATABASE_URL=... uv run python eval/retrieval_check.py

정답 문서를 하나로 특정하기는 어렵다. 대신 검색이 무너졌을 때 반드시 깨지는 것,
즉 **어느 체류자격의 문서를 물어왔는지**와 **핵심 낱말이 본문에 있는지**를 본다.
DATABASE_URL 이 없으면 BM25 단독으로 돌아가므로 점수가 낮게 나온다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nodes import qa                            # noqa: E402

# (질문, 체류자격, 상위 5개 안에 있어야 할 것)
#   visa=...  그 자격 또는 법령 조각이어야 한다
#   term=...  본문에 이 낱말 중 하나는 있어야 한다
CASES = [
    ("유학생인데 아르바이트 몇 시간까지 할 수 있어요?", "D-2", "시간제취업"),
    ("휴학하면 비자 어떻게 되나요?", "D-2", "휴학"),
    ("학교 옮기려면 어떻게 해요?", "D-2", "학교 변경"),
    ("이사했는데 신고해야 하나요?", "D-2", "체류지 변경"),
    ("체류기간 연장 서류 뭐 필요해요?", "D-2", "연장"),
    ("체류기간 연장 서류 뭐 필요해요?", "E-9", "연장"),
    ("사업장 옮길 수 있나요?", "E-9", "근무처"),
    ("결혼이민으로 자격 변경하려면요?", "F-6", "변경"),
    ("영주권 신청 요건이 뭔가요?", "F-5", "영주"),
    ("재입국허가 받아야 하나요?", "D-2", "재입국"),
    ("외국인등록 언제까지 해야 해요?", "D-2", "외국인등록"),
    ("체류기간 연장 수수료 얼마예요?", None, "수수료"),
    ("결핵진단서 내야 하나요?", None, "결핵"),
]

# 영문 질의는 번역을 거쳐야 한다. LLM 키가 없으면 번역기를 흉내내 배선만 확인한다.
EN_CASES = [
    ("How many hours can I work part-time as a student?", "D-2",
     "시간제취업 체류자격 외 활동 허용시간 유학생"),
    ("What documents do I need to extend my stay?", "E-9",
     "체류기간 연장허가 제출서류"),
    ("I moved to a new address, do I need to report it?", "D-2",
     "체류지 변경신고"),
]


def visa_ok(hit: dict, visa: str | None) -> bool:
    """자격 전용 문서라면 내 자격이어야 한다. 법령·공통사항은 언제나 통과."""
    tags = hit.get("visa") or []
    if not tags or not visa:
        return True
    return any(t.split("-")[:2] == visa.split("-")[:2] for t in tags)


def run(question: str, visa: str | None, term: str) -> tuple[bool, str, int]:
    """(통과, 설명, 다른 자격 조각 수)

    다른 자격 문서가 후보에 아예 없어야 하는 건 아니다 — "D-2에서 E-7으로
    바꾸려면?" 같은 질문은 상대 자격 문서를 봐야 답이 된다. 그래서 하드 필터가
    아니라 감점이다. 깨지면 안 되는 건 **내 자격 문서가 남의 것에 밀리지 않는 것**.
    """
    hits = qa.search(question, visa=visa)
    if not hits:
        return False, "검색 결과 없음", 0

    foreign = [i for i, h in enumerate(hits) if not visa_ok(h, visa)]
    mine = [i for i, h in enumerate(hits) if (h.get("visa") or []) and visa_ok(h, visa)]
    if foreign and mine and min(foreign) < max(mine):
        return False, f"{min(foreign) + 1}위가 다른 자격: {hits[min(foreign)]['cite']}", len(foreign)
    if not any(term.replace(" ", "") in h["text"].replace(" ", "") for h in hits):
        return False, f"'{term}' 이 상위 {len(hits)}건 어디에도 없음", len(foreign)

    tail = f"  (다른 자격 {len(foreign)}건이 뒤에 붙음)" if foreign else ""
    return True, hits[0]["cite"] + tail, len(foreign)


def main() -> None:
    live = bool(os.getenv("DATABASE_URL"))
    print(f"코퍼스 {qa._index()[5]}조각 | 벡터검색 {'ON' if live else 'OFF (BM25 단독)'}\n")

    fails = noise = 0
    print("── 한국어")
    for question, visa, term in CASES:
        ok, note, foreign = run(question, visa, term)
        fails += not ok
        noise += foreign
        print(f"  {'PASS' if ok else 'FAIL'}  [{visa or '-':4s}] {question}\n"
              f"        {note}")

    print("\n── 영어 (질의 번역 경유)")
    from app.tools import llm
    stub = {q: ko for q, _, ko in EN_CASES}
    if not llm.available():
        print("  ANTHROPIC_API_KEY 없음 — 번역 결과를 주입해 배선만 확인합니다.")
        llm.available = lambda: True
        llm.translate_query = lambda q: stub.get(q, "")
    for question, visa, _ in EN_CASES:
        got = qa._korean(question)
        ok, note, foreign = run(question, visa, "")
        fails += not ok
        noise += foreign
        print(f"  {'PASS' if ok else 'FAIL'}  [{visa}] {question}\n"
              f"        → {got}\n"
              f"        {note}")

    total = len(CASES) + len(EN_CASES)
    print(f"\n{total - fails}/{total} 통과  "
          f"(상위 {qa._TOP}건 중 다른 자격 조각 총 {noise}개 / {total * qa._TOP})")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
