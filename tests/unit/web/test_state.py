"""Private session state with the real adapter; no network requests."""

import pytest

from er_finder.web.live import RunnerBackend
from er_finder.web.state import WebSession


def test_default_backend_is_real_and_unconnected_input_has_no_invented_candidates():
    web = WebSession()
    assert isinstance(web.backend, RunnerBackend)
    web.submit("서울 강남구")
    assert web.result.reply is None
    assert web.result.note
    assert web.backend.profile.get_recent_visits() == []


def test_sessions_do_not_share_addresses_or_history():
    one, two = WebSession(), WebSession()
    one.set_home_address("서울 강남구", consent=True)
    one.submit("병원 조회")
    assert one.backend.user_id != two.backend.user_id
    assert two.backend.profile.get_home_address() is None
    assert two.messages == []


def test_reset_preserves_consented_address():
    web = WebSession()
    web.set_home_address("서울 강남구", consent=True)
    web.submit("병원 조회")
    web.reset()
    assert web.messages == []
    assert web.result is None
    assert web.backend.profile.get_home_address() == "서울 강남구"


def test_forget_removes_address_visits_and_dialogue():
    web = WebSession()
    web.set_home_address("서울 강남구", consent=True)
    web.backend.profile.add_visit(hpid="TEST", name="테스트 기관", symptom_summary="테스트")
    web.submit("병원 조회")
    web.forget()
    assert web.backend.profile.get_home_address() is None
    assert web.backend.profile.get_recent_visits() == []
    assert web.messages == []
    assert web.result is None


def test_consent_is_required_and_revocation_removes_address():
    web = WebSession()
    web.set_home_address("서울 강남구", consent=False)
    assert web.backend.profile.get_home_address() is None
    web.set_home_address("서울 강남구", consent=True)
    web.clear_home_address()
    assert web.backend.profile.get_home_address() is None


def test_transport_change_clears_old_context_and_rejects_unknown_transport():
    web = WebSession()
    web.submit("병원 조회")
    web.set_transport("walk")
    assert web.messages == []
    assert web.result is None
    with pytest.raises(ValueError):
        web.set_transport("invalid")


def test_display_redacts_common_personal_identifiers():
    web = WebSession()
    web.submit("연락처 010-1234-5678 주민번호 900101-1234567")
    visible = " ".join(message.text for message in web.messages)
    assert "010-1234-5678" not in visible
    assert "900101-1234567" not in visible


def test_blank_submission_and_unrequested_approval_do_nothing():
    web = WebSession()
    web.submit("  ")
    web.decide(True)
    assert web.messages == []
    assert web.result is None
    assert web.backend.profile.get_recent_visits() == []
