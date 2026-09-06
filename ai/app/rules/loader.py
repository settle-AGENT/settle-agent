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

# 이 앱이 무엇을 근거로 답하는지. /health 가 그대로 내보내므로, 떠 있는
# 컨테이너가 어느 판을 들고 있는지 밖에서 확인할 수 있다.
_SOURCES = _load("sources.yaml")
SOURCES_VERSION: str = _SOURCES.get("version", "unknown")
SOURCES: list[dict] = _SOURCES.get("sources", [])


def source_versions() -> dict[str, str]:
    """{자료 id: 판}. 낡았는지 판정하지는 않는다 — 그건 예약 점검의 몫이다."""
    return {s["id"]: str(s.get("version", "unknown")) for s in SOURCES}


def visa_spec(visa_type: str) -> dict:
    return VISA_MATRIX.get(visa_type, {})


def actions_for(visa_type: str) -> dict:
    return visa_spec(visa_type).get("actions", {})


def evidence_labels(ids: list[str]) -> list[str]:
    return [EVIDENCE[i]["law"] for i in ids if i in EVIDENCE]