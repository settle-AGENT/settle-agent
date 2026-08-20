from app.nodes.profiler import display_value, profile_to_payload, public_profile


def test_internal_account_enums_are_localized_at_user_boundary():
    profile = {
        "purpose": "living_expense",
        "income_source": "family_support",
    }

    assert public_profile(profile, "ko") == {
        "purpose": "생활비",
        "income_source": "가족 지원",
    }
    assert public_profile(profile, "en") == {
        "purpose": "Living expenses",
        "income_source": "Family support",
    }


def test_profile_confirmation_uses_labels_but_unknown_values_survive():
    payload = profile_to_payload(
        {"purpose": "tuition", "org_name": "Settle University"},
        {},
        "arc_front",
        locale="ko",
    )
    values = {field["key"]: field["value"] for field in payload["fields"]}

    assert values == {"purpose": "학비", "org_name": "Settle University"}
    assert display_value("purpose", "custom", "ko") == "custom"
