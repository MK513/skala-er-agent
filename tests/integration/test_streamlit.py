"""화면의 사용자 이벤트와 실제 메모리 저장 효과를 검증한다. 외부 API는 사용하지 않는다."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[2] / "streamlit_app.py"


def open_app(*, preview=True):
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not app.exception
    if preview:
        app.radio(key="mode").set_value("화면 검증용 데모").run()
        assert not app.exception
    return app


def search(app):
    app.chat_input(key="message").set_value("강남구, 손가락이 부었어요").run()
    assert not app.exception
    return app.session_state["web"]


def screen_text(app):
    return "\n".join(
        str(element.value)
        for kind in ("markdown", "caption", "info", "warning", "error", "success")
        for element in getattr(app, kind)
    )


def test_search_displays_synthetic_candidates_and_rerun_does_not_search_again():
    app = open_app()
    web = search(app)
    assert "화면 검증용 데모" in screen_text(app)
    assert "가상 응급센터 A" in screen_text(app)
    assert "가상 응급센터 C" in screen_text(app)
    assert "확인 불가" in screen_text(app)
    assert [h.hpid for h in web.result.reply.hospitals] == ["DEMO-001", "DEMO-002", "DEMO-003"]
    messages = list(web.messages)
    app.run()
    assert app.session_state["web"].messages == messages
    assert app.session_state["web"].backend.profile.get_recent_visits() == []


def test_visit_requires_click_approval_and_is_saved_only_once():
    app = open_app()
    web = search(app)
    app.button(key="select_DEMO-002").click().run()
    assert web.backend.profile.get_recent_visits() == []
    assert app.button(key="approve_visit")
    app.run()
    assert web.backend.profile.get_recent_visits() == []
    app.button(key="approve_visit").click().run()
    assert not app.exception
    visits = web.backend.profile.get_recent_visits()
    assert len(visits) == 1
    assert visits[0]["hpid"] == "DEMO-002"
    app.run()
    assert len(web.backend.profile.get_recent_visits()) == 1
    assert not any(button.key == "approve_visit" for button in app.button)


def test_reject_does_not_save_and_clears_approval_controls():
    app = open_app()
    web = search(app)
    app.button(key="select_DEMO-001").click().run()
    app.button(key="reject_visit").click().run()
    assert not app.exception
    assert web.backend.profile.get_recent_visits() == []
    assert not any(button.key == "approve_visit" for button in app.button)


def test_browser_sessions_do_not_share_history_or_visits():
    first, second = open_app(), open_app()
    first_web = search(first)
    first.button(key="select_DEMO-001").click().run()
    first.button(key="approve_visit").click().run()
    second.run()
    second_web = second.session_state["web"]
    assert first_web.backend.user_id != second_web.backend.user_id
    assert second_web.messages == []
    assert second_web.backend.profile.get_recent_visits() == []


def test_new_conversation_retains_profile_and_forget_removes_it():
    app = open_app()
    web = search(app)
    app.button(key="select_DEMO-001").click().run()
    app.button(key="approve_visit").click().run()
    app.button(key="new_conversation").click().run()
    assert web.messages == []
    assert web.result is None
    assert len(web.backend.profile.get_recent_visits()) == 1
    app.button(key="forget_all").click().run()
    assert not app.exception
    assert app.session_state["web"].backend.profile.get_recent_visits() == []


def test_home_address_needs_consent_and_can_be_removed():
    app = open_app()
    web = app.session_state["web"]
    app.text_input(key="home_address").set_value("서울특별시 강남구")
    app.button(key="save_home").click().run()
    assert web.backend.profile.get_home_address() is None
    assert "동의" in screen_text(app)
    app.checkbox(key="home_consent").check()
    app.button(key="save_home").click().run()
    assert not app.exception
    assert web.backend.profile.get_home_address() == "서울특별시 강남구"
    app.button(key="clear_home").click().run()
    assert web.backend.profile.get_home_address() is None


def test_transport_change_clears_previous_results_and_pending_approval():
    app = open_app()
    web = search(app)
    app.button(key="select_DEMO-001").click().run()
    app.selectbox(key="transport").set_value("walk").run()
    assert not app.exception
    assert web.transport == "walk"
    assert web.result is None
    assert web.backend.profile.get_recent_visits() == []
    assert not any(button.key == "approve_visit" for button in app.button)


def test_live_mode_is_blocked_and_never_shows_demo_results():
    app = open_app()
    search(app)
    app.radio(key="mode").set_value("실제 API").run()
    assert not app.exception
    assert app.chat_input(key="message").disabled
    assert app.button(key="run_scenario").disabled
    assert "연결" in screen_text(app)
    assert "가상 응급센터 A" not in screen_text(app)
    assert not any(button.key == "approve_visit" for button in app.button)


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("critical", "119"),
        ("stale", "갱신 지연"),
        ("error", "오류"),
        ("empty", "후보"),
        ("location", "위치"),
    ],
)
def test_scenario_status_is_visible_without_real_search(scenario, expected):
    app = open_app()
    app.selectbox(key="scenario").set_value(scenario).run()
    app.button(key="run_scenario").click().run()
    assert not app.exception
    assert expected in screen_text(app)
    assert "화면 검증용 데모" in screen_text(app)
    if scenario == "critical":
        assert any("119" in error.value for error in app.error)


def test_refresh_is_explicit_and_preserves_selected_scenario():
    app = open_app()
    web = search(app)
    app.button(key="refresh_search").click().run()
    assert not app.exception
    assert web.scenario == "candidates"
    assert [h.hpid for h in web.result.reply.hospitals] == ["DEMO-001", "DEMO-002", "DEMO-003"]
    assert web.backend.profile.get_recent_visits() == []


def test_backend_selection_error_does_not_expose_internal_request(monkeypatch):
    app = open_app()
    web = search(app)

    def unavailable(hpid):
        raise ValueError(f"INTERNAL_PRIVATE_REQUEST for {hpid}")

    monkeypatch.setattr(web.backend, "select_hospital", unavailable)
    app.button(key="select_DEMO-001").click().run()
    assert not app.exception
    assert app.error
    assert "INTERNAL_PRIVATE_REQUEST" not in screen_text(app)
    assert web.backend.profile.get_recent_visits() == []


@pytest.mark.parametrize(
    ("widget_type", "key", "value"),
    [
        ("selectbox", "scenario", "empty"),
        ("selectbox", "transport", "walk"),
        ("radio", "mode", "실제 API"),
    ],
)
def test_changed_context_and_approval_in_same_event_never_saves_old_plan(widget_type, key, value):
    app = open_app()
    web = search(app)
    app.button(key="select_DEMO-001").click().run()
    getattr(app, widget_type)(key=key).set_value(value)
    app.button(key="approve_visit").click().run()
    assert not app.exception
    assert web.backend.profile.get_recent_visits() == []
    assert web.result is None
    assert not any(button.key == "approve_visit" for button in app.button)


@pytest.mark.parametrize(("key", "value"), [("scenario", "empty"), ("transport", "walk")])
def test_scenario_button_uses_current_widget_context_in_same_event(key, value):
    app = open_app()
    app.selectbox(key=key).set_value(value)
    app.button(key="run_scenario").click().run()
    assert not app.exception
    web = app.session_state["web"]
    assert web.result is not None
    assert web.result.reply is not None
    if key == "scenario":
        assert web.result.reply.hospitals == []
    else:
        assert web.transport == "walk"


def test_default_screen_uses_live_mode_without_synthetic_results():
    app = open_app(preview=False)
    assert app.radio(key="mode").value == "실제 API"
    assert [tab.label for tab in app.tabs] == ["응급실 찾기", "의료 API 조회", "연결 상태"]
    assert app.chat_input(key="message").disabled
    assert app.button(key="connect_runner")
    assert "가상 응급센터" not in screen_text(app)
    assert app.session_state["web"].messages == []


def test_mode_switch_keeps_profiles_separate_and_clears_old_results():
    app = open_app()
    preview = search(app)
    preview.set_home_address("서울 강남구", consent=True)
    app.radio(key="mode").set_value("실제 API").run()
    live = app.session_state["web"]
    assert live is not preview
    assert live.backend.profile.get_home_address() is None
    assert live.result is None
    assert preview.result is None
    app.radio(key="mode").set_value("화면 검증용 데모").run()
    assert app.session_state["web"] is preview
    assert preview.backend.profile.get_home_address() == "서울 강남구"
    assert preview.result is None


def test_live_connection_failure_leaves_chat_disabled_without_fake_response():
    app = open_app(preview=False)
    app.button(key="connect_runner").click().run()
    assert not app.exception
    assert app.chat_input(key="message").disabled
    assert app.session_state["web"].result is None
    assert "가상 응급센터" not in screen_text(app)


def test_mode_change_with_address_save_does_not_write_the_previous_profile():
    app = open_app()
    preview = app.session_state["web"]
    app.text_input(key="home_address").set_value("서울 강남구")
    app.checkbox(key="home_consent").check()
    app.radio(key="mode").set_value("실제 API")
    app.button(key="save_home").click().run()
    assert not app.exception
    assert preview.backend.profile.get_home_address() is None
    assert app.session_state["web"].backend.profile.get_home_address() is None


def test_mode_change_with_address_delete_does_not_modify_the_previous_profile():
    app = open_app()
    preview = app.session_state["web"]
    preview.set_home_address("서울 강남구", consent=True)
    app.run()
    app.radio(key="mode").set_value("실제 API")
    app.button(key="clear_home").click().run()
    assert not app.exception
    assert preview.backend.profile.get_home_address() == "서울 강남구"


def test_forget_removes_both_modes_and_direct_api_history():
    app = open_app()
    for key in ("live_web", "preview_web"):
        app.session_state[key].set_home_address("서울 강남구", consent=True)
    app.session_state["api_lookup_result"] = {
        "lat": 37.5,
        "lon": 127.0,
        "radius": 5,
        "queried_at": "2026-09-11 14:00:00 KST",
        "rows": [],
        "error": False,
    }
    app.button(key="forget_all").click().run()
    assert not app.exception
    for key in ("live_web", "preview_web"):
        assert app.session_state[key].backend.profile.get_home_address() is None
    assert "api_lookup_result" not in app.session_state
