from app.agent.graph import ACTION_FIELDS, ask_visa, doc_builder
from app.agent import service
from app.agent.service import _document_intent, _guide, _normalize_phone_kr
from app.nodes.planner import build_task_graph


def test_mobile_subscription_asks_for_phone_number():
    assert ACTION_FIELDS["mobile_subscription"] == ["phone_kr"]


def test_mobile_subscription_completes_after_phone_is_saved():
    state = {
        "current_action": "mobile_subscription",
        "locale": "ko",
        "profile": {
            "visa_type": "D-2",
            "phone_kr": "010-1234-5678",
        },
    }

    result = doc_builder(state)

    assert result["completed"] == ["mobile_subscription"]
    assert result["current_action"] is None
    assert result["in_progress"] == []
    assert result["ui_type"] == "task_complete"
    assert result["ui_payload"]["phone_kr"] == "010-1234-5678"

    tasks = build_task_graph(
        state["profile"],
        completed=set(result["completed"]),
        locale="ko",
    )
    task = next(task for task in tasks if task["id"] == "mobile_subscription")
    assert task["status"] == "done"


def test_korean_mobile_number_requires_010_and_eleven_digits():
    assert _normalize_phone_kr("01012345678") == "010-1234-5678"
    assert _normalize_phone_kr("010-1234-5678") == "010-1234-5678"
    assert _normalize_phone_kr("053-945-345") is None
    assert _normalize_phone_kr("011-1234-5678") is None
    assert _normalize_phone_kr("010-123-5678") is None


REGISTERED = {
    "visa_type": "D-2",
    "arc_no": "990101-2345678",
    "passport_no": "M12345678",
}
UNREGISTERED = {
    "visa_type": "D-2",
    "passport_no": "M12345678",
}


def _stub_graph(monkeypatch, profile, tasks):
    """_guide 가 그래프를 태우지 않고 상태를 그대로 돌려받게 한다."""

    class GraphStub:
        def invoke(self, patch, _config):
            return {
                "session_id": "session-1",
                "locale": "ko",
                "profile": profile,
                "tasks": tasks,
                **patch,
            }

    monkeypatch.setattr(service, "_graph", lambda: GraphStub())
    monkeypatch.setattr(service, "_patch", lambda _session_id, extra: extra)
    monkeypatch.setattr(service, "_cfg", lambda _session_id: {})


def test_identity_fields_do_not_complete_a_form_task():
    """등록번호가 있어도 통합신청서 과제 자체가 done 이 되지는 않는다.

    앱이 만들 서류가 있는 과제는 executor 가 승인 뒤에 완료로 넣는다.
    """
    tasks = build_task_graph(REGISTERED, completed=set(), locale="ko")

    registration = next(t for t in tasks if t["id"] == "alien_registration")
    assert registration["status"] == "available"


def test_registration_number_unlocks_bank_account_without_the_form():
    """등록증을 가진 사람은 통합신청서를 거치지 않고 계좌개설로 간다.

    외국인등록번호는 등록을 마쳐야 나오는 번호다. 은행이 요구하는 것은
    등록된 사람인지이지, 이 앱으로 통합신청서를 만들었는지가 아니다.
    """
    tasks = build_task_graph(REGISTERED, completed=set(), locale="ko")

    bank = next(t for t in tasks if t["id"] == "open_bank_account")
    assert bank["status"] == "available"
    assert bank["blocked_by"] == []


def test_bank_account_stays_locked_without_registration_number():
    """아직 등록 전이면 계좌개설은 여전히 잠긴다. 무엇이 막는지도 밝힌다."""
    tasks = build_task_graph(UNREGISTERED, completed=set(), locale="ko")

    bank = next(t for t in tasks if t["id"] == "open_bank_account")
    assert bank["status"] == "locked"
    assert bank["blocked_by"] == ["외국인등록"]


def test_registered_user_is_offered_the_bank_form_directly(monkeypatch):
    tasks = build_task_graph(REGISTERED, completed=set(), locale="ko")
    _stub_graph(monkeypatch, REGISTERED, tasks)

    response = _guide("session-1", {}, tasks, "open_bank_account", "ko", REGISTERED)

    assert response["ui"] == {
        "type": "action_offer",
        "payload": {
            "action_id": "open_bank_account",
            "form": "bank_account_open",
            "label": "은행 계좌 개설",
        },
    }
    assert "통합신청서" not in response["reply"]


def test_locked_bank_account_routes_to_registration_form(monkeypatch):
    tasks = build_task_graph(UNREGISTERED, completed=set(), locale="ko")
    _stub_graph(monkeypatch, UNREGISTERED, tasks)

    response = _guide("session-1", {}, tasks, "open_bank_account", "ko", UNREGISTERED)

    assert response["ui"] == {
        "type": "action_offer",
        "payload": {
            "action_id": "alien_registration",
            "label": "통합신청서 작성하기",
            "form": "integrated_application",
        },
    }
    assert "3가지만" not in response["reply"]
    assert "통합신청서 작성 화면" in response["reply"]


def test_supported_document_questions_route_to_document_actions():
    profile = {"visa_type": "D-2"}
    tasks = build_task_graph(profile, completed={"alien_registration"}, locale="ko")

    assert _document_intent("계좌 개설 신청서가 필요해요", profile, tasks) == "open_bank_account"
    assert _document_intent("통합신청서를 작성하고 싶어요", profile, tasks) in {
        "alien_registration", "residence_change", "work_activity"
    }


def test_unsupported_document_questions_stay_in_chat():
    profile = {"visa_type": "D-2"}
    tasks = build_task_graph(profile, completed={"alien_registration"}, locale="ko")

    assert _document_intent("재학증명서는 학교에서 어떻게 발급해요?", profile, tasks) is None


def test_no_profile_explains_the_registration_route():
    """사진을 아직 안 올린 사람에게도 등록증이 없을 때의 길을 알려준다.

    "신분증을 올려주세요" 만 하면, 등록증이 없어서 물어본 사람은 답을 못 듣고
    막힌다. 계좌·통신은 대개 외국인등록이 선행이기 때문이다.
    """
    out = ask_visa({"locale": "ko", "profile": {}})

    assert out["ui_type"] == "none"
    assert "외국인등록" in out["reply"]
    assert "통합신청서" in out["reply"]


def test_no_profile_does_not_assume_the_user_lacks_a_card():
    """등록증을 이미 가진 사람도 이 문구를 본다. 단정하지 않고 촬영을 권한다."""
    out = ask_visa({"locale": "ko", "profile": {}})

    assert "외국인등록증이 있으시면" in out["reply"]
