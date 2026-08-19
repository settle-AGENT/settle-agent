"""rules/*.yaml 로더. import 시점에 한 번만 읽는다."""
from pathlib import Path
import yaml

RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


def _load(name: str) -> dict:
    return yaml.safe_load((RULES_DIR / name).read_text(encoding="utf-8"))


VISA_CODES = _load("visa_codes.yaml")["valid"]
VALID_VISA_CODES = set(VISA_CODES)

VISA_MATRIX = _load("visa_matrix.yaml")["visa"]
EVIDENCE = _load("evidence.yaml")


def actions_for(visa_type: str) -> dict:
    """해당 체류자격이 수행 가능한 액션 정의."""
    return VISA_MATRIX.get(visa_type, {}).get("actions", {})


def evidence_labels(ids: list[str]) -> list[str]:
    """근거 ID → 사람이 읽는 조문명."""
    return [EVIDENCE[i]["law"] for i in ids if i in EVIDENCE]