"""Planner — 체류자격 룰로 Task Graph를 계산한다.

이 파일에는 LLM이 없다. visa_matrix.yaml 이 모든 판단을 한다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.rules.loader import actions_for, evidence_labels, visa_spec

# 화면 표시 순서 (매트릭스 정의 순서를 그대로 따르되, 명시하면 이 순서 우선)
AGENCY_LABEL = {
    "immigration": "출입국·외국인청",
    "bank": "은행 영업점",
    "telecom": "통신사 대리점",
    "immigration_or_community_center": "출입국·외국인청 또는 주민센터",
}

DOC_LABEL = {
    "passport": "여권", "photo": "사진 1매", "arc": "외국인등록증",
    "enrollment_cert": "재학증명서", "residence_proof": "체류지 증빙",
    "employment_contract": "근로계약서", "business_registration": "사업자등록증",
}

ORDER = [
    "alien_registration",
    "mobile_subscription",
    "residence_change",
    "work_activity",
    "open_bank_account",
]
# 프로필에 이 값이 있으면 이미 해결된 것으로 본다 (D2에 visa_matrix로 이관)
SATISFIED_IF = {"mobile_subscription": "phone_kr"}

def _as_date(v) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _deadline(spec: dict, profile: dict, today: date) -> tuple[str | None, int | None]:
    """deadline: {days: 90, from: entry_date} → (YYYY-MM-DD, D-day)"""
    rule = spec.get("deadline")
    if not rule:
        return None, None

    base = _as_date(profile.get(rule.get("from")))
    if base is None:
        return None, None                      # 기준일을 아직 모름 → 질문 대상

    due = base + timedelta(days=int(rule["days"]))
    return due.isoformat(), (due - today).days


def _status(action_id: str, spec: dict, completed: set[str],
            in_progress: set[str], profile: dict | None = None) -> str:
    if action_id in completed:
        return "done"
    key = SATISFIED_IF.get(action_id)
    if key and (profile or {}).get(key):
        return "done"                      # 이미 갖고 있음 → 시킬 이유가 없다
    if action_id in in_progress:
        return "in_progress"
    if all(p in completed for p in spec.get("prereq", [])):
        return "available"
    return "locked"


def build_task_graph(
    profile: dict,
    completed: set[str] | None = None,
    in_progress: set[str] | None = None,
    today: date | None = None,
) -> list[dict]:
    """profile + 룰 → tasks[]

    반환 형태는 schemas.Task 와 1:1 이다.
    """
    completed = completed or set()
    in_progress = in_progress or set()
    today = today or date.today()

    visa = profile.get("visa_type")
    actions = actions_for(visa)
    if not actions:
        return []                              # 미지원 체류자격

    labels = {aid: s.get("label_ko", aid) for aid, s in actions.items()}
    ordered = [a for a in ORDER if a in actions] + \
              [a for a in actions if a not in ORDER]

    tasks: list[dict] = []
    for aid in ordered:
        spec = actions[aid]
        if spec.get("allowed") is False:
            continue                           # 이 자격으로는 불가한 액션

        status = _status(aid, spec, completed, in_progress, profile)
        prereq = spec.get("prereq", [])
        deadline, d_day = _deadline(spec, profile, today)

        tasks.append({
            "id": aid,
            "label": labels[aid],
            "status": status,
            "prereq": prereq,
            "blocked_by": [labels.get(p, p) for p in prereq
                           if p not in completed] if status == "locked" else [],
            "deadline": deadline,
            "d_day": d_day,
            "evidence": evidence_labels(spec.get("evidence", [])),
            # 화면에서 "어디에 뭘 들고 가야 하는지" 바로 보여주기 위한 값
            "agency": AGENCY_LABEL.get(spec.get("agency", ""), ""),
            "required_docs": [DOC_LABEL.get(d, d)
                              for d in spec.get("required_docs", [])],
            "note": spec.get("note_ko") or spec.get("condition_ko"),
        })

    # 기한이 임박한 것부터 위로, 그다음 원래 순서
        # 진행 중 → 지금 가능 → 잠김 → 완료. 같은 그룹 안에서는 기한 임박순.
    rank = {"in_progress": 0, "available": 1, "locked": 2, "done": 3}
    tasks.sort(key=lambda t: (rank.get(t["status"], 9),
                              t["d_day"] is None,
                              t["d_day"] if t["d_day"] is not None else 0))
    return tasks


def missing_for_deadlines(profile: dict, tasks: list[dict] | None = None) -> list[str]:
    """기한 계산에 필요한데 프로필에 없는 필드. 잠긴 액션은 제외한다."""
    tasks = tasks if tasks is not None else build_task_graph(profile)
    active = {t["id"] for t in tasks if t["status"] in ("available", "in_progress")}

    need: set[str] = set()
    for aid, spec in actions_for(profile.get("visa_type")).items():
        if aid not in active:
            continue
        rule = spec.get("deadline")
        if rule and not profile.get(rule.get("from")):
            need.add(rule["from"])
    return sorted(need)


def summary(tasks: list[dict]) -> str:
    """사용자에게 보여줄 한 줄 요약."""
    over = [t for t in tasks
            if t["status"] in ("available", "in_progress")
            and t["d_day"] is not None and t["d_day"] < 0]
    if over:
        t = over[0]
        return (f"{t['label']} 기한이 {abs(t['d_day'])}일 지났습니다. "
                f"지연 사유서가 필요할 수 있으니 {t['agency'] or '담당 기관'}에 "
                f"먼저 문의하세요.")

    urgent = next((t for t in tasks
                   if t["status"] == "available" and t["d_day"] is not None), None)
    avail = sum(1 for t in tasks if t["status"] == "available")
    if urgent:
        return (f"지금 하실 수 있는 일이 {avail}개 있습니다. "
                f"{urgent['label']}은(는) {urgent['d_day']}일 남았습니다.")
    if avail:
        return f"지금 하실 수 있는 일이 {avail}개 있습니다."
    return "먼저 완료해야 할 선행 절차가 있습니다."