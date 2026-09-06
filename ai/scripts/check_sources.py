"""근거 자료가 낡았는지, 선언과 실제가 어긋나지 않았는지 본다.

rules/sources.yaml 이 "이 앱은 무엇을 근거로 답하는가" 를 선언한다. 이 스크립트는
그 선언을 두 가지로 검사한다.

  정합성  선언한 판이 실제 파일과 맞는가.
          법령은 PDF 파일명의 시행일, 매뉴얼은 build_manual.py 의 상수,
          서식은 템플릿의 개정일 문구, 매트릭스는 자기 version 필드.
          어긋났다면 누군가 원본만 갈아끼우고 선언을 안 고친 것이다.

  노후도  마지막으로 확인한 지 recheck_after_days 가 지났는가.
          오래된 판이 곧 문제는 아니다 — 개정이 없었으면 3년 전 서식이 여전히
          최신이다. 문제는 확인한 지 오래된 것이다. 그래서 version 이 아니라
          last_verified 를 본다.

둘 다 네트워크를 쓰지 않는다. 실제로 원본이 개정됐는지 확인하려면 국가법령정보
센터 OPEN API 가 필요하고, 그건 아직 붙이지 않았다 — README 참고.

사용
  uv run python scripts/check_sources.py
      사람이 읽는 표. 문제가 있으면 종료코드 1.

  uv run python scripts/check_sources.py --format github
      GitHub 이슈 본문용 마크다운. 워크플로가 이것을 쓴다.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

AI_ROOT = Path(__file__).resolve().parents[1]
SOURCES = AI_ROOT / "rules" / "sources.yaml"

# 법령 PDF 파일명 끝의 (YYYYMMDD) 가 시행일이다.
_PDF_DATE = re.compile(r"\((\d{8})\)\.pdf$")
# build_manual.py 의 LAW_FULL 상수에 박힌 판.  ...「외국인체류 안내매뉴얼」(2026. 8.)
_MANUAL_VERSION = re.compile(r"「외국인체류 안내매뉴얼」\s*\(\s*(\d{4})\.\s*(\d{1,2})\.")
# 서식 템플릿의 개정일.  <개정 2022. 4. 12.>
_FORM_VERSION = re.compile(r"개정\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.")


# 대조할 로컬 파일이 없어 정합성 검사를 건너뛴다는 표시. None(=읽지 못함)과
# 구분해야 한다 — 전자는 정상이고 후자는 문제다.
SKIP = object()


class Finding:
    """검사에 걸린 것 하나."""

    def __init__(self, source_id: str, kind: str, message: str):
        self.source_id = source_id
        self.kind = kind            # "mismatch" | "stale" | "missing"
        self.message = message


def _load() -> dict:
    return yaml.safe_load(SOURCES.read_text(encoding="utf-8"))


def _actual_version(source: dict) -> tuple[str | None, str]:
    """실제 파일에서 읽은 판. (값, 어디서 읽었는지) — 읽을 수 없으면 (None, 이유)."""
    kind = source.get("kind")

    if kind == "statute":
        name = source.get("file")
        if not name:
            # 코퍼스에 넣지 않고 지켜보기만 하는 법령(예: 시행규칙). 대조할
            # 로컬 파일이 없으니 정합성은 건너뛰고 노후도만 본다.
            return SKIP, "로컬 사본 없음 — 노후도만 본다"
        path = AI_ROOT / name
        if not path.exists():
            return None, f"{name} 이 없다"
        m = _PDF_DATE.search(path.name)
        if not m:
            return None, f"{path.name} 에서 시행일을 읽지 못했다"
        raw = m.group(1)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}", path.name

    if kind == "manual":
        path = AI_ROOT / source["declared_in"]
        if not path.exists():
            return None, f"{source['declared_in']} 이 없다"
        m = _MANUAL_VERSION.search(path.read_text(encoding="utf-8"))
        if not m:
            return None, f"{source['declared_in']} 에서 판을 읽지 못했다"
        return f"{m.group(1)}-{int(m.group(2)):02d}", source["declared_in"]

    if kind == "form":
        path = AI_ROOT / source["declared_in"]
        if not path.exists():
            return None, f"{source['declared_in']} 이 없다"
        m = _FORM_VERSION.search(path.read_text(encoding="utf-8"))
        if not m:
            return None, f"{source['declared_in']} 에서 개정일을 읽지 못했다"
        return (f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
                source["declared_in"])

    if kind == "internal":
        path = AI_ROOT / source["declared_in"]
        if not path.exists():
            return None, f"{source['declared_in']} 이 없다"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return str(data.get("version") or ""), source["declared_in"]

    return None, f"모르는 kind: {kind}"


def _as_date(value: str) -> date | None:
    """last_verified 전용. 날짜까지 적힌 것만 받는다.

    월까지만 적힌 값("2026-09")도 받아 주면 1일로 채워지고, 그만큼 노후도가
    최대 한 달 어긋난다. version 은 매뉴얼처럼 월 단위인 것이 있어 문자열로
    비교하지만, last_verified 는 "며칠 지났나" 를 재는 값이라 날짜가 있어야
    한다. 형식이 어긋나면 통과시키지 않고 읽지 못했다고 알린다.
    """
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def check(today: date | None = None) -> tuple[list[dict], list[Finding]]:
    """(검사한 자료들, 걸린 것들)."""
    today = today or date.today()
    data = _load()
    rows: list[dict] = []
    findings: list[Finding] = []

    for source in data.get("sources", []):
        declared = str(source.get("version", ""))
        actual, where = _actual_version(source)

        if actual is SKIP:
            pass                       # 대조할 사본이 없다. 문제가 아니다.
        elif actual is None:
            findings.append(Finding(source["id"], "missing", where))
        elif actual != declared:
            findings.append(Finding(
                source["id"], "mismatch",
                f"선언 {declared} · 실제 {actual} ({where})"))

        verified = _as_date(source.get("last_verified", ""))
        limit = int(source.get("recheck_after_days", 365))
        age = (today - verified).days if verified else None
        if verified is None:
            findings.append(Finding(source["id"], "missing",
                                    "last_verified 를 읽지 못했다"))
        elif age < 0:
            # 앞선 날짜면 age 가 음수라 age > limit 을 영영 넘지 못한다. 오타
            # 하나로 그 자료가 재확인 대상에서 조용히 빠진다 — 지금까지 고쳐 온
            # "통과했지만 확인되지 않은" 부류와 같은 종류의 구멍이다.
            findings.append(Finding(
                source["id"], "future",
                f"last_verified 가 오늘보다 {abs(age)}일 앞서 있다 ({verified})"))
        elif age > limit:
            findings.append(Finding(
                source["id"], "stale",
                f"확인한 지 {age}일 지났다 (기준 {limit}일)"))

        rows.append({
            "id": source["id"], "name": source["name"],
            "kind": source.get("kind", ""), "version": declared,
            "actual": None if actual is SKIP else actual,
            "unverified": actual is SKIP,
            "age": age, "limit": limit,
        })

    return rows, findings


_LABEL = {"mismatch": "선언과 실제가 다름", "stale": "확인 필요",
          "missing": "읽지 못함", "future": "앞선 날짜"}


def render_text(rows: list[dict], findings: list[Finding]) -> str:
    out = [f"{'자료':<34} {'판':<12} {'확인 후':>8}  상태"]
    out.append("-" * 72)
    bad = {f.source_id for f in findings}
    for r in rows:
        age = f"{r['age']}일" if r["age"] is not None else "?"
        if r["id"] in bad:
            mark = "!"
        elif r["unverified"]:
            # 통과했다고 맞다는 뜻이 아니다. 대조할 사본이 없어 아무도 확인하지
            # 않은 값이라는 뜻이다. 실제로 여기 틀린 시행일이 하나 들어가 있었고,
            # "ok" 로 보였기 때문에 읽는 사람도 그냥 지나쳤다.
            mark = "미대조"
        else:
            mark = "ok"
        out.append(f"{r['name'][:33]:<34} {r['version']:<12} {age:>8}  {mark}")

    unverified = [r for r in rows if r["unverified"] and r["id"] not in bad]
    if unverified:
        out.append("")
        out.append("  미대조 — 로컬 사본이 없어 선언한 값을 대조하지 못했다. "
                   "원본과 맞는지는 사람이 봐야 한다.")
        for r in unverified:
            out.append(f"    {r['id']} = {r['version']}")

    if findings:
        out.append("")
        for f in findings:
            out.append(f"  [{_LABEL[f.kind]}] {f.source_id} — {f.message}")
    return "\n".join(out)


def render_github(rows: list[dict], findings: list[Finding]) -> str:
    """이슈 본문. 무엇을 해야 하는지까지 적는다 — 알림만 오면 아무도 안 움직인다."""
    out = ["근거 자료 점검에서 아래가 걸렸습니다.", ""]
    out.append("| 자료 | 선언한 판 | 문제 |")
    out.append("|---|---|---|")
    by_id = {r["id"]: r for r in rows}
    for f in findings:
        row = by_id.get(f.source_id, {})
        out.append(f"| {row.get('name', f.source_id)} | `{row.get('version', '?')}` "
                   f"| **{_LABEL[f.kind]}** — {f.message} |")

    # 아래 안내문은 리스트 안에서 여러 줄로 이어 붙인다. 괄호로 묶지 않으면
    # 콤마 하나를 빠뜨렸을 때 두 항목이 조용히 한 문장으로 합쳐진다.
    out += ["", "### 무엇을 하면 되나", ""]
    if any(f.kind == "stale" for f in findings):
        out += [
            ("**확인 필요** — 원본이 개정됐는지 사람이 봐야 합니다. 법령은 "
             "[국가법령정보센터](https://www.law.go.kr), 매뉴얼·서식은 "
             "[하이코리아](https://www.hikorea.go.kr) 자료실입니다."),
            "",
            "- 그대로면 `ai/rules/sources.yaml` 의 `last_verified` 만 오늘 날짜로 올립니다.",
            ("- 바뀌었으면 원본을 교체하고 `version` 과 `last_verified` 를 함께 "
             "올립니다. 코퍼스 재생성은 `ai/README.md` 를 따릅니다."),
            "",
        ]
    if any(f.kind == "mismatch" for f in findings):
        out += [
            ("**선언과 실제가 다름** — 원본만 갈아끼우고 `sources.yaml` 을 안 "
             "고쳤을 때 납니다. 둘 중 맞는 쪽으로 맞춰 주세요."),
            "",
        ]
    if any(f.kind == "future" for f in findings):
        out += [
            ("**앞선 날짜** — `last_verified` 가 오늘보다 뒤입니다. 오타일 "
             "가능성이 큽니다. 그대로 두면 그 자료는 재확인 대상에서 계속 "
             "빠집니다."),
            "",
        ]
    if any(f.kind == "missing" for f in findings):
        out += [
            ("**읽지 못함** — 파일이 없거나 형식이 바뀌었습니다. 검사기가 "
             "낡았을 수도 있으니 `ai/scripts/check_sources.py` 도 함께 보세요."),
            "",
        ]
    out.append("서식이 바뀌었다면 템플릿만이 아니라 `ai/mappings/*.yaml` 의 필드 매핑과 "
               "`ai/rules/visa_matrix.yaml` 의 `required_docs` 도 함께 봐야 합니다.")
    return "\n".join(out)


# 종료코드로 세 가지를 구분한다. 부르는 쪽(워크플로)이 "문제 없음" 과
# "점검기가 깨짐" 을 섞으면, 낡은 자료를 몇 달이고 못 알아챈다.
OK, FINDINGS, BROKEN = 0, 1, 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "github"), default="text")
    args = parser.parse_args()

    # 본문이 한국어라 콘솔 인코딩에 걸린다. Windows 기본(cp949)에서는 em dash
    # 하나에 print 가 죽고, 그러면 종료코드 1 이 나가 "지적 있음" 과 구별되지
    # 않는다 — 워크플로가 빈 본문으로 이슈를 연다. 출력을 UTF-8 로 고정한다.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    try:
        rows, findings = check()
        text = (render_github(rows, findings) if args.format == "github"
                else render_text(rows, findings))
        if args.format == "text" or findings:
            print(text)
        return FINDINGS if findings else OK
    except Exception as exc:                                  # noqa: BLE001
        # 자료가 멀쩡하다는 뜻이 아니라, 멀쩡한지 알 수 없다는 뜻이다.
        print(f"점검기 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
        return BROKEN


if __name__ == "__main__":
    sys.exit(main())
