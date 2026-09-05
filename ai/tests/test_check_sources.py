"""근거 자료 점검기가 실제로 잡아내는지.

항상 "ok" 만 내는 검사기는 없느니만 못하다. 어긋남과 노후를 각각 만들어
걸리는지 본다.
"""
from datetime import date

import pytest

from scripts import check_sources


def test_declared_versions_match_the_actual_files():
    """rules/sources.yaml 의 선언이 실제 파일과 맞는가.

    노후(stale)는 보지 않는다 — 날짜가 지나면 참이 되는 값이라, 그것까지
    막으면 관계없는 PR 이 달력 때문에 멈춘다. 노후는 예약 워크플로가 알린다.
    """
    _, findings = check_sources.check()

    drift = [f for f in findings if f.kind in ("mismatch", "missing")]
    assert drift == [], "\n".join(f"{f.source_id}: {f.message}" for f in drift)


def test_mismatch_is_detected(monkeypatch):
    """선언한 판이 실제 파일과 다르면 잡는다."""
    monkeypatch.setattr(check_sources, "_load", lambda: {"sources": [{
        "id": "visa_matrix", "name": "체류자격 매트릭스", "kind": "internal",
        "version": "1900-01-01",                  # 실제 파일과 다르다
        "last_verified": "2026-09-05",
        "recheck_after_days": 180,
        "declared_in": "rules/visa_matrix.yaml",
    }]})

    _, findings = check_sources.check(today=date(2026, 9, 5))

    assert [f.kind for f in findings] == ["mismatch"]
    assert "1900-01-01" in findings[0].message


def test_staleness_is_measured_from_last_verified(monkeypatch):
    """오래된 판이 아니라, 확인한 지 오래된 것을 잡는다."""
    source = {
        "id": "integrated_application_form", "name": "통합신청서", "kind": "form",
        "version": "2022-04-12",                  # 판은 오래됐지만
        "last_verified": "2026-09-01",            # 확인은 최근이다
        "recheck_after_days": 365,
        "declared_in": "templates/integrated_application.html",
    }
    monkeypatch.setattr(check_sources, "_load", lambda: {"sources": [source]})

    _, fresh = check_sources.check(today=date(2026, 9, 5))
    assert fresh == [], "판이 오래됐다는 이유만으로 울리면 안 된다"

    _, stale = check_sources.check(today=date(2027, 9, 5))
    assert [f.kind for f in stale] == ["stale"]


def test_missing_file_is_reported(monkeypatch):
    monkeypatch.setattr(check_sources, "_load", lambda: {"sources": [{
        "id": "gone", "name": "없는 것", "kind": "statute",
        "version": "2026-01-01", "last_verified": "2026-09-05",
        "recheck_after_days": 180,
        "file": "corpus/없는파일(법률)(제1호)(20260101).pdf",
    }]})

    _, findings = check_sources.check(today=date(2026, 9, 5))

    assert [f.kind for f in findings] == ["missing"]


@pytest.mark.parametrize("kind", ["mismatch", "stale", "missing"])
def test_issue_body_says_what_to_do(kind):
    """알림만 오고 무엇을 할지 없으면 아무도 안 움직인다."""
    rows = [{"id": "x", "name": "어떤 자료", "kind": "statute",
             "version": "2026-01-01", "actual": None, "age": 1, "limit": 180}]
    body = check_sources.render_github(rows, [check_sources.Finding("x", kind, "…")])

    assert "무엇을 하면 되나" in body
    assert "어떤 자료" in body


def test_a_broken_checker_is_not_reported_as_clean(monkeypatch, capsys):
    """점검기가 깨졌을 때 "문제 없음" 과 같은 종료코드를 내면 안 된다.

    실제로 그럴 뻔했다. 본문이 한국어라 Windows 기본 콘솔(cp949)에서 print 가
    죽었고, 그때 종료코드 1 이 나가 "지적 있음" 과 구별되지 않았다. 워크플로는
    그것을 지적으로 읽고 빈 본문의 이슈를 연다.
    """
    def boom():
        raise RuntimeError("sources.yaml 이 깨졌다")

    monkeypatch.setattr(check_sources, "_load", boom)
    monkeypatch.setattr("sys.argv", ["check_sources.py", "--format", "github"])

    code = check_sources.main()

    assert code == check_sources.BROKEN
    assert code not in (check_sources.OK, check_sources.FINDINGS)
    assert "점검기 실패" in capsys.readouterr().err


def test_findings_and_clean_use_distinct_exit_codes(monkeypatch):
    monkeypatch.setattr("sys.argv", ["check_sources.py"])
    monkeypatch.setattr(check_sources, "check",
                        lambda today=None: ([], [check_sources.Finding("x", "stale", "…")]))
    assert check_sources.main() == check_sources.FINDINGS

    monkeypatch.setattr(check_sources, "check", lambda today=None: ([], []))
    assert check_sources.main() == check_sources.OK
