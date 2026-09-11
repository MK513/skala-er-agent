from __future__ import annotations

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.memory import InMemorySaver

from er_finder.memory.session import SessionManager


@pytest.fixture
def checkpointer():
    return InMemorySaver()


@pytest.fixture
def session(checkpointer):
    return SessionManager(checkpointer=checkpointer)


def _create_checkpoint(checkpointer: InMemorySaver, session: SessionManager, user_id: str) -> None:
    # 실제로는 create_agent 실행 중 LangGraph가 자동으로 만들어주는 체크포인트를
    # raw API로 직접 하나 찍어서 has_active_session이 True가 되는 경로를 재현한다.
    config = session.build_config(user_id)
    config = {
        **config,
        "configurable": {**config["configurable"], "checkpoint_ns": ""},
    }
    checkpointer.put(config, empty_checkpoint(), {}, {})


def test_build_config_uses_user_id_as_thread_id(session):
    assert session.build_config("u123") == {"configurable": {"thread_id": "u123"}}


@pytest.mark.parametrize("bad_user_id", ["", "   "])
def test_build_config_rejects_empty_user_id(session, bad_user_id):
    with pytest.raises(ValueError):
        session.build_config(bad_user_id)


def test_has_active_session_false_before_any_checkpoint(session):
    assert session.has_active_session("u123") is False


def test_has_active_session_true_after_checkpoint_created(checkpointer, session):
    _create_checkpoint(checkpointer, session, "u123")
    assert session.has_active_session("u123") is True


def test_has_active_session_isolated_per_user(checkpointer, session):
    _create_checkpoint(checkpointer, session, "u123")
    assert session.has_active_session("u456") is False


def test_reset_session_removes_checkpoint(checkpointer, session):
    _create_checkpoint(checkpointer, session, "u123")
    assert session.has_active_session("u123") is True

    session.reset_session("u123")

    assert session.has_active_session("u123") is False


def test_reset_session_on_nonexistent_session_is_a_noop(session):
    session.reset_session("u_nonexistent")  # 에러 없이 통과해야 함


def test_end_session_removes_checkpoint(checkpointer, session):
    _create_checkpoint(checkpointer, session, "u123")

    session.end_session("u123")

    assert session.has_active_session("u123") is False


def test_end_session_on_nonexistent_session_is_a_noop(session):
    session.end_session("u_nonexistent")  # 에러 없이 통과해야 함


def test_reset_session_does_not_affect_other_users(checkpointer, session):
    _create_checkpoint(checkpointer, session, "u123")
    _create_checkpoint(checkpointer, session, "u456")

    session.reset_session("u123")

    assert session.has_active_session("u123") is False
    assert session.has_active_session("u456") is True
