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


# ── seed 고정물 ────────────────────────────────────────────
# 페르소나 값을 코드에 또 적지 않는다. seed 가 한 곳의 출처이고, 여기서는
# 그것이 실제로 돌아가는지만 본다 — 갈라지면 이 테스트가 먼저 깨진다.
SEED = Path(__file__).resolve().parents[2] / "seed"


def _seed(name: str):
    import json
    return json.loads((SEED / name).read_text(encoding="utf-8"))


def test_seed_e9_files_exist():
    for name in ("arc_e9_front.jpg", "arc_e9_back.jpg", "passport_e9.jpg",
                 "mrz_e9.txt", "profile_e9.json", "tasks_e9.json"):
        assert (SEED / name).is_file(), f"seed/{name} 이 없다"


def test_seed_e9_mrz_checksums_are_valid():
    """체크섬이 틀린 MRZ 를 넣어 두면 파서 테스트가 통과할 수 없다."""
    line2 = (SEED / "mrz_e9.txt").read_text(encoding="utf-8").splitlines()[1]
    weights = (7, 3, 1)

    def check(s: str) -> str:
        total = 0
        for i, ch in enumerate(s):
            v = int(ch) if ch.isdigit() else (0 if ch == "<" else ord(ch) - 55)
            total += v * weights[i % 3]
        return str(total % 10)

    passport, p_c = line2[:9], line2[9]
    birth, b_c = line2[13:19], line2[19]
    expiry, e_c = line2[21:27], line2[27]
    personal, pe_c = line2[28:42], line2[42]

    assert check(passport) == p_c
    assert check(birth) == b_c
    assert check(expiry) == e_c
    assert check(personal) == pe_c
    assert check(passport + p_c + birth + b_c + expiry + e_c + personal + pe_c) == line2[43]


def test_seed_e9_profile_matches_the_card_images():
    profile = _seed("profile_e9.json")

    assert profile["visa_type"] == "E-9"
    assert profile["arc_no"] == "950312-5234567"     # 앞면에 인쇄된 값
    assert profile["stay_expiry"] == "2027-06-30"    # 뒷면에 인쇄된 값
    assert profile["nationality"] == "NPL"


def test_seed_e9_tasks_match_what_the_planner_actually_produces():
    """손으로 고친 고정물은 조용히 거짓말을 한다. 매번 다시 계산해 맞춘다."""
    profile = _seed("profile_e9.json")
    expected = _seed("tasks_e9.json")

    actual = build_task_graph(profile, today=date(2026, 9, 19), locale="ko")

    assert [t["id"] for t in actual] == [t["id"] for t in expected]
    for got, want in zip(actual, expected):
        for key in ("label", "status", "deadline", "d_day", "evidence"):
            assert got[key] == want[key], f"{got['id']}.{key}"
