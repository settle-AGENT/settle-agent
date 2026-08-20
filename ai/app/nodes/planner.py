"""Planner — 체류자격 룰로 Task Graph를 계산한다.

이 파일에는 LLM이 없다. visa_matrix.yaml 이 모든 판단을 한다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.rules.loader import actions_for, evidence_labels, visa_spec

# 화면 표시 순서 (매트릭스 정의 순서를 그대로 따르되, 명시하면 이 순서 우선)
AGENCY_LABEL = {
    "immigration": {"ko": "출입국·외국인청", "en": "Immigration Office"},
    "bank": {"ko": "은행 영업점", "en": "Bank branch"},
    "telecom": {"ko": "통신사 대리점", "en": "Mobile carrier store"},
    "immigration_or_community_center": {
        "ko": "출입국·외국인청 또는 주민센터",
        "en": "Immigration Office or community service center"},
}

DOC_LABEL = {
    "passport": {"ko": "여권", "en": "Passport"},
    "photo": {"ko": "사진 1매", "en": "One photo"},
    "arc": {"ko": "외국인등록증", "en": "Alien Registration Card"},
    "enrollment_cert": {"ko": "재학증명서", "en": "Enrollment certificate"},
    "residence_proof": {"ko": "체류지 증빙", "en": "Proof of residence"},
    "employment_contract": {"ko": "근로계약서", "en": "Employment contract"},
    "business_registration": {"ko": "사업자등록증", "en": "Business registration"},
}


def _pick(table: dict, key: str, locale: str, default: str = "") -> str:
    """{ko, en} 테이블에서 locale 을 고른다. 모르는 키는 default."""
    entry = table.get(key)
    if not entry:
        return default
    return entry.get(locale) or entry["en"]


def _field(spec: dict, base: str, locale: str) -> str | None:
    """룰의 base_ko / base_en 중 locale 것. 영어가 없으면 한국어로 떨어뜨린다 —
    빈 값을 내보내는 것보다 낫다."""
    return spec.get(f"{base}_{locale}") or spec.get(f"{base}_ko")

ORDER = [
    "alien_registration",
    "mobile_subscription",
    "residence_change",
    "work_activity",
    "open_bank_account",
]
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
            in_progress: set[str]) -> str:
    if action_id in completed:
        return "done"
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
    locale: str = "en",
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

    # 프로필에 값이 있으면 이미 끝낸 것으로 본다. 등록증 번호를 들고 있는데
    # 외국인등록을 하라고 시키면 사용자는 앱을 믿지 않는다.
    #
    # completed 에 합쳐 넣는 것이 핵심이다. 상태만 done 으로 바꾸면 그것을
    # 선행조건으로 삼는 과제들이 계속 잠겨 있다 — 등록은 끝났는데 계좌는
    # 영영 안 열리는 상태가 된다.
    completed = set(completed)
    for aid, spec in actions.items():
        key = spec.get("satisfied_if")
        if key and profile.get(key):
            completed.add(aid)

    labels = {aid: _field(s, "label", locale) or aid
              for aid, s in actions.items()}
    ordered = [a for a in ORDER if a in actions] + \
              [a for a in actions if a not in ORDER]

    tasks: list[dict] = []
    for aid in ordered:
        spec = actions[aid]
        if spec.get("allowed") is False:
            continue                           # 이 자격으로는 불가한 액션

        status = _status(aid, spec, completed, in_progress)
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
            "agency": _pick(AGENCY_LABEL, spec.get("agency", ""), locale),
            "required_docs": [_pick(DOC_LABEL, d, locale, d)
                              for d in spec.get("required_docs", [])],
            "note": _field(spec, "note", locale) or _field(spec, "condition", locale),
        })

    # 기한이 임박한 것부터 위로, 그다음 원래 순서
        # 진행 중 → 지금 가능 → 잠김 → 완료. 같은 그룹 안에서는 기한 임박순.
    rank = {"in_progress": 0, "available": 1, "locked": 2, "done": 3}
    tasks.sort(key=lambda t: (rank.get(t["status"], 9),
                              t["d_day"] is None,
                              t["d_day"] if t["d_day"] is not None else 0))
    return tasks


MENU_TITLE = {"ko": "무엇을 도와드릴까요?", "en": "What can I help you with?"}
_MENU_NOTE = {
    "locked": {"ko": "{}\u00a0후 가능", "en": "after {}"},
    "dday":   {"ko": "D-{}", "en": "D-{}"},
    "over":   {"ko": "{}일 지남", "en": "{} days overdue"},
}


def menu_options(tasks: list[dict], locale: str = "en") -> list[dict]:
    """할 수 있는 일 목록. select 옵션 형태로 돌려준다.

    고정 목록이 아니다 — 체류자격에 따라 항목이 달라지고, 끝낸 과제는 빠지며,
    잠긴 과제는 무엇 때문에 잠겼는지 라벨에 실린다. 화면에 보이는 것이 곧
    지금 이 사람의 상태다.
    """
    def note(t: dict) -> str | None:
        if t["status"] == "locked" and t.get("blocked_by"):
            return _MENU_NOTE["locked"][locale].format(t["blocked_by"][0])
        d = t.get("d_day")
        if d is None:
            return None
        key = "over" if d < 0 else "dday"
        return _MENU_NOTE[key][locale].format(abs(d))

    out = []
    for t in tasks:
        if t["status"] == "done":
            continue                       # 끝난 일을 다시 권하지 않는다
        tail = note(t)
        out.append({
            "value": t["id"],
            "label": f"{t['label']} · {tail}" if tail else t["label"],
        })
    return out


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