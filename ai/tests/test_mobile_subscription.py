from app.agent.graph import ACTION_FIELDS, doc_builder
from app.agent.service import _document_intent, _normalize_phone_kr
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


def test_document_form_is_not_completed_by_uploaded_identity_fields():
    tasks = build_task_graph(
        {
            "visa_type": "D-2",
            "arc_no": "990101-2345678",
            "passport_no": "M12345678",
        },
        completed=set(),
        locale="ko",
    )

    registration = next(task for task in tasks if task["id"] == "alien_registration")
    bank = next(task for task in tasks if task["id"] == "open_bank_account")

    assert registration["status"] == "available"
    assert bank["status"] == "locked"


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
