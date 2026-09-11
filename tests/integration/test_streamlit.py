"""Application startup, configuration and private session controls without API calls."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from er_finder.web import api_view, live

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[2] / "streamlit_app.py"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        api_view, "credential_status", lambda: {key: False for key in live.REQUIRED_KEYS}
    )
    monkeypatch.setattr(
        live, "credential_status", lambda: {key: False for key in live.REQUIRED_KEYS}
    )
    result = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not result.exception
    return result


def test_startup_has_only_real_service_views_and_no_preview_controls(app):
    assert [tab.label for tab in app.tabs] == ["의료기관 조회", "에이전트 상담", "연결 상태"]
    assert not app.radio
    assert not any(widget.key == "scenario" for widget in app.selectbox)
    assert not any(button.key == "run_scenario" for button in app.button)
    assert not (APP.parent / "src/er_finder/web/preview.py").exists()
    assert app.session_state["web"].messages == []
    assert app.chat_input(key="message").disabled


def test_missing_keys_block_agent_and_api_calls_without_crashing(app):
    app.button(key="connect_runner").click().run()
    assert not app.exception
    assert app.chat_input(key="message").disabled
    assert app.button(key="api_search").disabled
    assert app.session_state["web"].result is None


def test_address_requires_consent_and_can_be_removed(app):
    web = app.session_state["web"]
    app.text_input(key="home_address").set_value("서울 강남구")
    app.button(key="save_home").click().run()
    assert web.backend.profile.get_home_address() is None
    app.checkbox(key="home_consent").check()
    app.button(key="save_home").click().run()
    assert web.backend.profile.get_home_address() == "서울 강남구"
    app.button(key="clear_home").click().run()
    assert web.backend.profile.get_home_address() is None
    assert not app.exception


def test_browser_sessions_keep_profiles_separate(app):
    first = app.session_state["web"]
    first.set_home_address("서울 강남구", consent=True)
    second = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not second.exception
    other = second.session_state["web"]
    assert first.backend.user_id != other.backend.user_id
    assert other.backend.profile.get_home_address() is None


def test_forget_removes_profile_and_api_lookup_records(app):
    web = app.session_state["web"]
    web.set_home_address("서울 강남구", consent=True)
    app.session_state["api_lookup_result"] = {
        "lat": 37.5,
        "lon": 127.0,
        "radius": 5,
        "queried_at": "test",
        "rows": [],
        "error": False,
    }
    app.button(key="forget_all").click().run()
    assert not app.exception
    assert web.backend.profile.get_home_address() is None
    assert "api_lookup_result" not in app.session_state
