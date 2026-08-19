"""rules/*.yaml 로더. import 시점에 한 번만 읽는다."""
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


def _load(name: str) -> dict:
    return yaml.safe_load((RULES_DIR / name).read_text(encoding="utf-8"))


VISA_CODES: dict = _load("visa_codes.yaml")["valid"]
VALID_VISA_CODES: set[str] = set(VISA_CODES)

_MATRIX = _load("visa_matrix.yaml")
VISA_MATRIX: dict = _MATRIX["visa"]
MATRIX_VERSION: str = _MATRIX.get("version", "unknown")

EVIDENCE: dict = _load("evidence.yaml")


def visa_spec(visa_type: str) -> dict:
    return VISA_MATRIX.get(visa_type, {})


def actions_for(visa_type: str) -> dict:
    return visa_spec(visa_type).get("actions", {})


def evidence_labels(ids: list[str]) -> list[str]:
    return [EVIDENCE[i]["law"] for i in ids if i in EVIDENCE]