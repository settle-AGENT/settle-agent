from pathlib import Path

from pypdf import PdfReader

from app.nodes import doc_builder
from app.rules.loader import actions_for


PROFILE = {
    "name_en": "KIM MINJI",
    "arc_no": "990101-2345678",
    "nationality": "VNM",
    "birth_date": "1999-01-01",
    "visa_type": "D-2",
    "stay_expiry": "2027-08-31",
    "addr_kr": "Seoul Mapo-gu",
    "phone_kr": "010-1234-5678",
    "org_name": "Settle University",
    "purpose": "tuition",
    "income_source": "family_support",
}


def test_open_bank_account_action_selects_bank_account_form():
    assert actions_for("D-2")["open_bank_account"]["form"] == "bank_account_open"


def test_bank_account_pdf_is_created_without_review_or_rule_annotations(
    tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(doc_builder, "OUTPUT_DIR", tmp_path)

    result = doc_builder.render(
        "bank_account_open",
        PROFILE,
        confidence={"addr_kr": 0.5},
        doc_id="bank-account-test",
        locale="ko",
    )

    assert result["pdf_path"] is not None
    assert Path(result["pdf_path"]).is_file()
    assert result["title"] == "외국인 계좌개설 신청서"
    assert result["low_confidence"] == ["addr_kr"]

    html = Path(result["html_path"]).read_text(encoding="utf-8")
    assert "Seoul Mapo-gu" in html
    assert "확인 필요" not in html
    assert "확인필요" not in html
    assert "#fff3cd" not in html
    assert "특정금융정보법 제5조의2" not in html
    assert "근거:" not in html

    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(result["pdf_path"]).pages
    )
    assert "Seoul Mapo-gu" in pdf_text
    assert "확인 필요" not in pdf_text
    assert "특정금융정보법 제5조의2" not in pdf_text


def test_integrated_application_html_has_no_review_annotations(
    tmp_path: Path, monkeypatch,
):
    monkeypatch.setattr(doc_builder, "OUTPUT_DIR", tmp_path)

    result = doc_builder.render(
        "integrated_application",
        PROFILE,
        confidence={"addr_kr": 0.5},
        variant="registration",
        doc_id="integrated-test",
        locale="ko",
    )

    html = Path(result["html_path"]).read_text(encoding="utf-8")
    assert "Seoul Mapo-gu" in html
    assert "확인 필요" not in html
    assert "확인필요" not in html
    assert "#fff7d6" not in html
