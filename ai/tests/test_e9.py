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


# ── 추출기 · 실제 E-9 등록증 OCR 결과 ──────────────────────
# 아래 두 덩어리는 인도네시아 국적 E-9 등록증을 CLOVA OCR 에 실제로 태워
# 받은 인식 결과다. 지어낸 것이 아니므로, 여기서 깨지면 실제로 깨진다.
OCR_FRONT = """KOR
외국인등록증
RESIDENCE CARD
Registration No.
외국인등록번호
001130-8678945
성명
SITI
Name
(시티)
국가/지역
INDONESIA
Country / Region
PHOTO
Status
체류자격
비전문취업 (E-9)
허가일 / 만료일
2026.07.01. / 2029.06.30.
Permission / Expiry
체류지
전라남도 영암군 삼호읍 대불로 88
Address
발급일자
Issue Date 2026.07.01.
서울출입국
외국인청장인
서울출입국 · 외국인청장
CHIEF, SEOUL IMMIGRATION OFFICE""".splitlines()

OCR_BACK = """체류자격 및 체류기간
STATUS / PERIOD OF SOJOURN
체류기간 만료일
체류자격 Status
비전문취업 (E-9)
2029.06.30.
Period of sojourn until
체류지 CHANGE OF RESIDENCE
신고일자 Date
체류지 Address
2026.07.01.
전라남도 영암군 삼호읍 대불로 88
근무처 PLACE OF EMPLOYMENT
신고일자 Date
근무처 Employer
2026.07.01.
대불조선기자재(주)
발행국
Issuing Country
KOR
IC CHIP / 안전칩
일련번호
Serial No.
9944550066""".splitlines()


def test_ocr_reads_e9_as_e9():
    """체류자격을 못 읽으면 그 뒤 룰 엔진이 통째로 헛돈다."""
    from app.extractors.arc import parse_rules

    front, _ = parse_rules(OCR_FRONT, "arc_front")
    back, _ = parse_rules(OCR_BACK, "arc_back")

    assert front["visa_type"] == "E-9"
    assert back["visa_type"] == "E-9"
    assert front["arc_no"] == "001130-8678945"
    assert front["nationality"] == "IDN"
    assert back["stay_expiry"] == "2029-06-30"      # 두 날짜 중 늦은 쪽


def test_a_single_word_name_is_read():
    """성 없이 이름 하나만 쓰는 사람이 있다 — 인도네시아가 그렇고, 고용허가제
    송출국이다. 이름을 못 읽으면 신청서의 성명란이 빈다."""
    from app.extractors.arc import parse_rules

    profile, confidence = parse_rules(OCR_FRONT, "arc_front")

    assert profile["name_en"] == "SITI"
    # 한 낱말은 표제어를 잘못 집을 수 있어 사용자 확인을 거쳐야 한다
    assert confidence["name_en"] < 0.9


def test_a_multi_word_name_still_wins_over_a_single_word_one():
    """한 낱말을 허용하면서 여러 낱말 이름이 밀리면 그게 더 큰 손해다."""
    from app.extractors.arc import parse_rules

    texts = ["KOR 외국인등록증 RESIDENCE CARD", "990101-5123456",
             "성명", "NGUYEN VAN A", "Name", "국가/지역", "VIETNAM"]
    profile, confidence = parse_rules(texts, "arc_front")

    assert profile["name_en"] == "NGUYEN VAN A"
    assert confidence["name_en"] > 0.9


def test_employer_is_read_from_the_back_of_the_card():
    """근무처가 카드에 찍혀 있는데 되물으면 반복 입력을 줄인다는 말이 거짓이 된다."""
    from app.extractors.arc import parse_rules

    profile, _ = parse_rules(OCR_BACK, "arc_back")

    assert profile["org_name"] == "대불조선기자재(주)"


def test_reading_the_employer_does_not_pollute_the_address():
    """근무처 칸이 생기면서 주소 뒤에 라벨이 따라붙을 수 있다."""
    from app.extractors.arc import _trim_addr, parse_rules

    profile, _ = parse_rules(OCR_BACK, "arc_back")

    assert _trim_addr(profile["addr_kr"]) == "전라남도 영암군 삼호읍 대불로 88"
