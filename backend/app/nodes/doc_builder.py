"""DocBuilder — profile + mapping YAML → HTML → PDF

원칙
  - LLM 을 쓰지 않는다. 값 생성은 전부 결정적 매핑이다.
  - 렌더에는 마스킹하지 않은 평문 프로필을 쓴다 (서버 내부에서만 생성된다).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

BACKEND_DIR = Path(__file__).resolve().parents[2]
MAPPING_DIR = BACKEND_DIR / "mappings"
TEMPLATE_DIR = BACKEND_DIR / "templates"
OUTPUT_DIR = BACKEND_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

CONF_THRESHOLD = 0.90

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

COUNTRY_NAME = {
    "VNM": "VIETNAM", "CHN": "CHINA", "UZB": "UZBEKISTAN", "NPL": "NEPAL",
    "MNG": "MONGOLIA", "PHL": "PHILIPPINES", "IDN": "INDONESIA",
    "THA": "THAILAND", "KHM": "CAMBODIA", "MMR": "MYANMAR", "JPN": "JAPAN",
    "USA": "UNITED STATES", "IND": "INDIA", "BGD": "BANGLADESH",
}

DOC_LABELS = {
    "passport": "여권", "photo": "사진 1매", "arc": "외국인등록증",
    "enrollment_cert": "재학증명서", "residence_proof": "체류지 증빙",
    "employment_contract": "근로계약서", "business_registration": "사업자등록증",
}

CDD_FIELDS = {"residency_status", "purpose", "income_source", "account_type"}


class DocumentIncomplete(Exception):
    """필수 필드가 비어 서류를 만들 수 없다."""

    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"missing required fields: {', '.join(missing)}")


def load_mapping(form: str) -> dict:
    path = MAPPING_DIR / f"{form}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"mapping not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def compute_residency(profile: dict) -> str:
    """외국환거래규정상 거주자·비거주자 판정 (데모 단순화)."""
    return "거주자" if profile.get("visa_type") and profile.get("stay_expiry") else "비거주자"


def _resolve(spec: dict, profile: dict, rule_values: dict) -> Any:
    src: str = spec.get("from", "")
    if src.startswith("profile."):
        value = profile.get(src.split(".", 1)[1])
    elif src.startswith("rule."):
        value = rule_values.get(src.split(".", 1)[1])
    else:
        value = None

    if value in (None, ""):
        return None
    if spec.get("transform") == "country_name":
        value = COUNTRY_NAME.get(str(value).upper(), value)
    if enum := spec.get("enum"):
        value = enum.get(str(value), value)
    return value


def _required(spec: dict, variant: str) -> bool:
    if spec.get("required"):
        return True
    cond = spec.get("required_when")
    if cond and cond.startswith("variant !="):
        return variant != cond.split("!=", 1)[1].strip()
    return False


def build_rows(form: str, profile: dict, confidence: dict | None = None,
               variant: str = "default", account_type: str = "limited"
               ) -> tuple[dict, list[dict], list[str]]:
    """(meta, rows, missing). 렌더 전에 검증할 수 있다."""
    meta = load_mapping(form)
    confidence = confidence or {}
    rule_values = {
        "residency_status": compute_residency(profile),
        "account_type": account_type,
    }

    rows: list[dict] = []
    missing: list[str] = []

    for key, spec in meta["fields"].items():
        value = _resolve(spec, profile, rule_values)
        if value is None and _required(spec, variant):
            missing.append(key)

        conf = confidence.get(key, 1.0)
        rows.append({
            "key": key,
            "label_ko": spec.get("label_ko", key),
            "label_en": spec.get("label_en", ""),
            "value": value,
            "low_conf": conf < CONF_THRESHOLD,
            "note": ("확인 필요" if conf < CONF_THRESHOLD else None),
            "evidence": spec.get("evidence"),
            "group": "cdd" if key in CDD_FIELDS else "identity",
        })

    return meta, rows, missing


def _flat(profile: dict, rule_values: dict) -> dict:
    """별지 제34호서식이 요구하는 칸 단위 값으로 펼친다."""
    name = (profile.get("name_en") or "").strip()
    parts = name.split()
    surname = parts[0] if parts else ""
    given = " ".join(parts[1:]) if len(parts) > 1 else ""

    birth = (profile.get("birth_date") or "").split("-")
    by, bm, bd = (birth + ["", "", ""])[:3]

    return {
        "surname": surname,
        "given_names": given,
        "birth_y": by, "birth_m": bm, "birth_d": bd,
        "sex": profile.get("gender", ""),
        "nationality": COUNTRY_NAME.get(str(profile.get("nationality", "")).upper(),
                                        profile.get("nationality", "")),
        "arc_no": profile.get("arc_no", ""),
        "passport_no": profile.get("passport_no", ""),
        "passport_issue_date": profile.get("passport_issue", ""),
        "passport_expiry": profile.get("passport_expiry", ""),
        "sex": profile.get("gender", ""),
        "addr_kr": profile.get("addr_kr", ""),
        "tel_kr": profile.get("tel_kr", ""),
        "phone_kr": profile.get("phone_kr", ""),
        "addr_home": profile.get("addr_home_country", ""),
        "phone_home": profile.get("phone_home", ""),
        "school_name": profile.get("org_name", ""),
        "school_phone": profile.get("school_phone", ""),
        "workplace": profile.get("workplace", ""),
        "biz_no": profile.get("biz_reg_no", ""),
        "work_phone": profile.get("work_phone", ""),
        "income": profile.get("annual_income", ""),
        "occupation": profile.get("occupation", ""),
        "email": profile.get("email", ""),
        "refund_account": profile.get("refund_account", ""),
        "visa_type": profile.get("visa_type", ""),
        "stay_expiry": profile.get("stay_expiry", ""),
        "residency_status": rule_values.get("residency_status", ""),
        "account_type": rule_values.get("account_type", ""),
    }


def render(form: str, profile: dict, *,
           confidence: dict | None = None,
           variant: str = "default",
           required_docs: list[str] | None = None,
           account_type: str = "limited",
           doc_id: str | None = None,
           strict: bool = True) -> dict:
    """서류를 생성한다.

    returns: {document_id, title, html_path, pdf_path, missing, low_confidence}
    """
    meta, rows, missing = build_rows(form, profile, confidence, variant, account_type)

    if missing and strict:
        raise DocumentIncomplete(missing)

    variants = meta.get("variants") or {}
    vspec = variants.get(variant) or next(iter(variants.values()), {})

    rule_values = {
        "residency_status": compute_residency(profile),
        "account_type": account_type,
    }

    html = _env.get_template(meta["template"]).render(
        meta=meta,
        rows=rows,
        f=_flat(profile, rule_values),
        low=[],          # 경고 표시는 서류에 인쇄하지 않는다. 화면에서만 알린다.
        variant=variant,
        desired_status=profile.get("desired_status"),
        today=date.today().isoformat(),
        required_docs=[DOC_LABELS.get(d, d) for d in (required_docs or [])],
        fee=vspec.get("fee"),
    )

    doc_id = doc_id or f"doc-{form}-{variant}"
    html_path = OUTPUT_DIR / f"{doc_id}.html"
    pdf_path = OUTPUT_DIR / f"{doc_id}.pdf"
    html_path.write_text(html, encoding="utf-8")

    try:
        from weasyprint import HTML
        HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf(str(pdf_path))
        pdf_ok = True
    except Exception as exc:                                   # noqa: BLE001
        print(f"[doc_builder] PDF 생성 실패(HTML 은 생성됨): {exc!r}")
        pdf_ok = False

    return {
        "document_id": doc_id,
        "title": meta["title_ko"],
        "html_path": str(html_path),
        "pdf_path": str(pdf_path) if pdf_ok else None,
        "missing": missing,
        "low_confidence": [r["key"] for r in rows if r["low_conf"]],
    }
