"""Test the actual-mode UI and RunnerBackend contract with an injected fake runner.

These tests exercise the UI adapter and shared memory store, not a real LLM,
external API, or LangGraph HITL interrupt/resume implementation.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from er_finder.memory.store import ERFinderStore
from er_finder.web import live
from er_finder.web.contracts import UIReply
from er_finder.web.state import WebSession

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[2] / "streamlit_app.py"
QUERY = "강남역, 손가락이 부었어요"


class FakeRunner:
    """A deterministic runner-port double; only its approved action writes memory."""

    def __init__(self, *, user_id, transport, store):
        self.profile = ERFinderStore(store, user_id)
        self.transport = transport
        self.calls = []
        self.approvals = []
        self.pending = False
        self.reply = UIReply(
            severity="standard",
            call_119_first=False,
            search_radius_km=5,
            hospitals=[
                dict(
                    hpid="UI-TEST-001",
                    name="오프라인 테스트 병원",
                    distance_km=1.2,
                    er_beds_available=2,
                    beds_updated_at="2026-09-11T09:00:00+09:00",
                    address="오프라인 테스트 주소",
                )
            ],
            data_timestamp="2026-09-11T09:00:00+09:00",
            next_action="방문 전 전화로 확인하세요.",
        )

    def chat(self, text, *, force_refresh=False):
        self.calls.append((text, force_refresh))
        self.pending = text == "1번"
        pending = None
        if self.pending:
            pending = dict(
                hpid="UI-TEST-001",
                name="오프라인 테스트 병원",
                symptom_summary="오프라인 테스트 증상",
            )
        return SimpleNamespace(reply=self.reply, pending_approval=pending, note=None)

    def approve(self, approved):
        assert self.pending
        self.approvals.append(approved)
        self.pending = False
        if approved:
            self.profile.add_visit(
                hpid="UI-TEST-001",
                name="오프라인 테스트 병원",
                symptom_summary="오프라인 테스트 증상",
            )
        return SimpleNamespace(reply=self.reply, pending_approval=None, note="결정 처리 완료")

    def end_session(self):
        self.pending = False


@pytest.fixture
def connected_app(monkeypatch):
    monkeypatch.setattr(
        live, "credential_status", lambda: {key: True for key in live.REQUIRED_KEYS}
    )
    runners = []

    def factory(**kwargs):
        runner = FakeRunner(**kwargs)
        runners.append(runner)
        return runner

    backend = live.RunnerBackend(runner_factory=factory)
    web = WebSession(backend=backend)
    app = AppTest.from_file(str(APP), default_timeout=10)
    app.session_state["web"] = web
    app.run()
    assert not app.exception
    assert app.chat_input(key="message").disabled
    assert runners == []

    app.button(key="connect_runner").click().run()
    assert not app.exception
    assert not app.chat_input(key="message").disabled
    assert len(runners) == 1
    assert runners[0].calls == []
    return app, web, runners[0]


def select_candidate(app, web):
    app.chat_input(key="message").set_value(QUERY).run()
    assert not app.exception
    assert web.result.reply.hospitals[0].hpid == "UI-TEST-001"
    app.button(key="select_UI-TEST-001").click().run()
    assert not app.exception
    assert web.result.pending_approval.hpid == "UI-TEST-001"
    assert app.chat_input(key="message").disabled
    assert web.backend.profile.get_recent_visits() == []


def test_live_ui_approval_writes_shared_store_once_and_rerun_does_not_repeat(connected_app):
    app, web, runner = connected_app
    select_candidate(app, web)
    app.run()
    assert runner.calls == [(QUERY, False), ("1번", False)]
    assert runner.approvals == []
    assert web.backend.profile.get_recent_visits() == []

    app.button(key="approve_visit").click().run()
    assert not app.exception
    assert runner.approvals == [True]
    assert [visit["hpid"] for visit in web.backend.profile.get_recent_visits()] == ["UI-TEST-001"]
    assert web.result.pending_approval is None
    assert not app.chat_input(key="message").disabled
    assert not any(button.key == "approve_visit" for button in app.button)
    app.run()
    assert runner.calls == [(QUERY, False), ("1번", False)]
    assert runner.approvals == [True]
    assert len(web.backend.profile.get_recent_visits()) == 1


def test_live_ui_rejection_never_saves_or_repeats_on_rerun(connected_app):
    app, web, runner = connected_app
    select_candidate(app, web)
    app.button(key="reject_visit").click().run()
    assert not app.exception
    assert runner.approvals == [False]
    assert web.result.pending_approval is None
    assert not any(button.key in {"approve_visit", "reject_visit"} for button in app.button)
    app.run()
    assert runner.calls == [(QUERY, False), ("1번", False)]
    assert runner.approvals == [False]
    assert web.backend.profile.get_recent_visits() == []


def test_transport_change_and_approval_in_same_event_never_saves_previous_plan(connected_app):
    app, web, runner = connected_app
    select_candidate(app, web)
    app.selectbox(key="transport").set_value("walk")
    app.button(key="approve_visit").click().run()
    assert not app.exception
    assert app.session_state["web"] is web
    assert web.result is None
    assert runner.approvals == []
    assert web.backend.profile.get_recent_visits() == []
    assert app.session_state["web"].backend.profile.get_recent_visits() == []
    assert not any(button.key == "approve_visit" for button in app.button)
    app.run()
    assert runner.calls == [(QUERY, False), ("1번", False)]
    assert runner.approvals == []


def test_live_ui_only_explicit_refresh_repeats_the_query(connected_app):
    app, web, runner = connected_app
    app.chat_input(key="message").set_value(QUERY).run()
    assert not app.exception
    app.run()
    assert runner.calls == [(QUERY, False)]
    app.button(key="refresh_search").click().run()
    assert not app.exception
    assert runner.calls == [(QUERY, False), (QUERY, True)]
    app.run()
    assert runner.calls == [(QUERY, False), (QUERY, True)]
    assert runner.approvals == []
    assert web.backend.profile.get_recent_visits() == []


def test_coordinate_input_is_sent_to_runner_and_changed_location_cancels_approval(connected_app):
    app, web, runner = connected_app
    app.checkbox(key="use_coordinates").check().run()
    app.number_input(key="chat_lat").set_value(37.5)
    app.number_input(key="chat_lon").set_value(127.0)
    app.chat_input(key="message").set_value("손가락이 부었어요").run()
    assert runner.calls[-1][0] == "37.500000, 127.000000 손가락이 부었어요"
    app.button(key="select_UI-TEST-001").click().run()
    assert web.result.pending_approval is not None
    app.number_input(key="chat_lat").set_value(37.6)
    app.button(key="approve_visit").click().run()
    assert not app.exception
    assert runner.approvals == []
    assert web.result is None
    assert web.backend.profile.get_recent_visits() == []
