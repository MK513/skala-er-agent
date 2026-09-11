"""Verify user-visible state and real memory writes without a model or API."""

import pytest

from er_finder.web.state import WebSession


def test_preview_search_returns_explicit_synthetic_candidates_without_saving():
    web = WebSession()
    web.submit("서울 강남구 역삼동입니다")
    assert [hospital.hpid for hospital in web.result.reply.hospitals] == [
        "DEMO-001",
        "DEMO-002",
        "DEMO-003",
    ]
    assert all(hospital.er_tel is None for hospital in web.result.reply.hospitals)
    assert web.backend.profile.get_recent_visits() == []


def test_selection_requires_approval_and_cannot_save_twice():
    web = WebSession()
    web.submit("시연")
    web.select_hospital("DEMO-002")
    assert web.result.pending_approval.hpid == "DEMO-002"
    assert web.backend.profile.get_recent_visits() == []
    web.decide(True)
    assert web.backend.profile.get_recent_visits()[0]["hpid"] == "DEMO-002"
    assert web.result.pending_approval is None
    web.decide(True)
    assert len(web.backend.profile.get_recent_visits()) == 1


def test_rejection_does_not_save():
    web = WebSession()
    web.submit("시연")
    web.submit("두 번째 병원으로 갈게요")
    web.decide(False)
    assert web.backend.profile.get_recent_visits() == []
    assert web.result.pending_approval is None


def test_separate_browsers_cannot_share_dialogue_or_profile():
    one, two = WebSession(), WebSession()
    one.set_home_address("시연 주소", consent=True)
    one.submit("시연")
    one.select_hospital("DEMO-001")
    one.decide(True)
    assert one.backend.user_id != two.backend.user_id
    assert two.backend.profile.get_home_address() is None
    assert two.backend.profile.get_recent_visits() == []
    assert two.messages == []


def test_reset_cancels_pending_but_preserves_consented_profile():
    web = WebSession()
    web.set_home_address("시연 주소", consent=True)
    web.submit("시연")
    web.select_hospital("DEMO-001")
    web.reset()
    web.decide(True)
    assert web.backend.profile.get_recent_visits() == []
    assert web.backend.profile.get_home_address() == "시연 주소"
    assert web.messages == []


def test_forget_removes_profile_visits_and_dialogue():
    web = WebSession()
    web.set_home_address("시연 주소", consent=True)
    web.submit("시연")
    web.select_hospital("DEMO-001")
    web.decide(True)
    web.forget()
    assert web.backend.profile.get_home_address() is None
    assert web.backend.profile.get_recent_visits() == []
    assert web.messages == []
    assert web.result is None


def test_address_consent_is_required_and_can_be_revoked():
    web = WebSession()
    web.set_home_address("시연 주소", consent=False)
    assert web.backend.profile.get_home_address() is None
    assert web.result.note
    web.set_home_address("시연 주소", consent=True)
    web.clear_home_address()
    assert web.backend.profile.get_home_address() is None


@pytest.mark.parametrize("change", ["scenario", "transport", "refresh"])
def test_new_search_context_cancels_pending_and_cannot_reuse_old_approval(change):
    web = WebSession()
    web.submit("시연")
    web.select_hospital("DEMO-001")
    if change == "scenario":
        web.set_scenario("empty")
    elif change == "transport":
        web.set_transport("walk")
    else:
        web.refresh()
    web.decide(True)
    assert web.backend.profile.get_recent_visits() == []


def test_unknown_or_old_candidate_never_produces_approval():
    web = WebSession()
    web.submit("시연")
    web.select_hospital("invented-hospital")
    assert web.result.pending_approval is None
    web.set_scenario("empty")
    web.submit("시연")
    web.select_hospital("DEMO-001")
    assert web.result.pending_approval is None


def test_error_clears_old_candidates_and_exposes_no_raw_exception():
    web = WebSession()
    web.submit("시연")
    web.set_scenario("error")
    web.submit("시연")
    assert web.result.reply is None
    assert web.result.note
    assert "Traceback" not in web.result.note


def test_location_case_can_continue_and_refresh_does_not_repeat_selection():
    web = WebSession()
    web.set_scenario("location")
    web.submit("위치 없는 시연 입력")
    assert not web.result.reply.hospitals
    web.submit("서울 강남구 역삼동입니다")
    assert len(web.result.reply.hospitals) == 3
    web.select_hospital("DEMO-002")
    web.refresh()
    assert web.result.pending_approval is None
    assert len(web.result.reply.hospitals) == 3
    assert web.backend.profile.get_recent_visits() == []


def test_display_redacts_common_phone_and_registration_number():
    web = WebSession()
    web.submit("연락처 010-1234-5678 주민번호 900101-1234567")
    visible = " ".join(message.text for message in web.messages)
    assert "010-1234-5678" not in visible
    assert "900101-1234567" not in visible


def test_blank_submission_does_not_create_a_turn():
    web = WebSession()
    web.submit("  ")
    assert web.messages == []
    assert web.result is None
