"""E-9(비전문취업) 지원이 실제로 살아 있는지.

D-2 와 같은 코드 경로를 타지만 결론이 달라야 하는 지점만 본다 — 과제 목록이
비지 않는가, 시간제취업을 권하지 않는가, 서류가 재학증명서가 아닌가, 사업장
이름이 서식의 학교 칸이 아니라 근무처 칸에 찍히는가.
"""
from datetime import date
from pathlib import Path

from app.agent import graph
from app.nodes import doc_builder
from app.nodes.planner import build_task_graph
from app.rules.loader import actions_for

PROFILE = {
    "name_en": "NGUYEN VAN A",
    "arc_no": "990101-5234567",
    "nationality": "VNM",
    "birth_date": "1999-01-01",
    "visa_type": "E-9",
    "entry_date": "2026-08-15",
    "stay_expiry": "2027-08-14",
    "addr_kr": "Ansan Danwon-gu",
    "phone_kr": "010-1234-5678",
    "org_name": "Settle Manufacturing Co.",
    "purpose": "salary",
    "income_source": "part_time",
}


def test_e9_has_a_task_graph():
    """매트릭스에 E-9 이 없던 시절에는 여기가 빈 목록이었다."""
    tasks = build_task_graph(PROFILE, today=date(2026, 9, 19), locale="ko")

    assert tasks, "E-9 프로필인데 할 수 있는 일이 하나도 없다"
    assert {t["id"] for t in tasks} >= {
        "alien_registration", "mobile_subscription",
        "residence_change", "open_bank_account",
    }


def test_e9_is_not_offered_the_student_part_time_permit():
    """고용허가제는 허가받은 사업장에서만 일한다. 시간제취업을 권하면 오안내다."""
    tasks = build_task_graph(PROFILE, today=date(2026, 9, 19), locale="ko")

    assert actions_for("E-9")["work_activity"]["allowed"] is False
    assert "work_activity" not in {t["id"] for t in tasks}


def test_e9_registration_asks_for_employment_documents_not_enrollment():
    docs = actions_for("E-9")["alien_registration"]["required_docs"]

    assert "business_registration" in docs
    assert "enrollment_cert" not in docs
    assert "enrollment_cert" not in actions_for("E-9")["open_bank_account"]["required_docs"]


def test_e9_workplace_lands_in_the_workplace_box_not_the_school_box(
    tmp_path: Path, monkeypatch,
):
    """별지 34호서식에는 학교 칸과 근무처 칸이 따로 있다."""
    monkeypatch.setattr(doc_builder, "OUTPUT_DIR", tmp_path)

    result = doc_builder.render(
        "integrated_application", PROFILE,
        variant="registration", doc_id="e9-registration", locale="ko",
    )
    html = Path(result["html_path"]).read_text(encoding="utf-8")

    school_cell, workplace_cell = html.split("근무처", 1)
    assert "Settle Manufacturing Co." in workplace_cell
    assert "Settle Manufacturing Co." not in school_cell


def test_unsupported_visa_message_lists_what_is_actually_supported():
    """코드에 목록을 박아 두면 매트릭스를 고쳐도 문구가 낡는다."""
    supported = graph.supported_visas("ko")

    assert "D-2" in supported and "E-9" in supported

    said = graph._text(graph.VISA_UNSUPPORTED, "ko").format("F-6", supported)
    assert "E-9" in said


def test_e9_is_asked_about_a_workplace_not_a_school():
    asked = graph._question("org_name", "E-9")["label"]["ko"]

    assert "학교" not in asked
    assert graph._question("org_name", "D-2")["label"]["ko"] != asked
