"""agent/runner.py(ERFinder) 검증.

guardrails/memory/search/safety 쪽 실제 구현은 아직 없으므로 conftest.py의
runner_module/make_finder 픽스처가 최소 스텁을 심어 runner.py만 독립적으로 돌린다.
LLM 모델은 어디에서도 호출하지 않는다 - create_agent 자체를 MagicMock으로 바꿔서
만든 가짜 그래프(finder.graph)의 invoke()만 호출되며, 그 반환값은 각 테스트가 직접 정한다.
"""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


def test_chat_raises_when_text_is_empty_after_masking(make_finder, runner_module, monkeypatch):
    finder = make_finder()
    monkeypatch.setattr(runner_module, "mask_pii", lambda text: "   ")

    with pytest.raises(ValueError):
        finder.chat("아무 의미 없는 입력")


def test_chat_triggers_on_emergency_callback_when_severity_is_critical(
    make_finder, runner_module, monkeypatch, make_assessment
):
    on_emergency = MagicMock()
    finder = make_finder(on_emergency=on_emergency)
    finder.classifier.assess.return_value = make_assessment(severity="critical")
    monkeypatch.setattr(runner_module, "selected_index", lambda text: None)

    finder.chat("의식이 없어요, 마포구 합정동")

    on_emergency.assert_called_once_with(runner_module.EMERGENCY)


def test_chat_does_not_trigger_emergency_callback_for_standard_severity(
    make_finder, runner_module, monkeypatch, make_assessment
):
    on_emergency = MagicMock()
    finder = make_finder(on_emergency=on_emergency)
    finder.classifier.assess.return_value = make_assessment(severity="standard")
    monkeypatch.setattr(runner_module, "selected_index", lambda text: None)

    finder.chat("발목을 삐었어요")

    on_emergency.assert_not_called()


def test_chat_sets_history_note_when_user_asks_about_past_visit(
    make_finder, runner_module, monkeypatch, make_assessment
):
    finder = make_finder()
    finder.classifier.assess.return_value = make_assessment()
    monkeypatch.setattr(runner_module, "selected_index", lambda text: None)
    finder.profiles.recent_visits.return_value = [{"name": "서울병원"}]

    result = finder.chat("지난번 병원 어디였지?")

    assert "서울병원" in result.note


def test_chat_history_note_when_no_saved_visits(
    make_finder, runner_module, monkeypatch, make_assessment
):
    finder = make_finder()
    finder.classifier.assess.return_value = make_assessment()
    monkeypatch.setattr(runner_module, "selected_index", lambda text: None)
    finder.profiles.recent_visits.return_value = []

    result = finder.chat("최근 방문 기록 알려줘")

    assert result.note == "저장된 방문 기록이 없습니다."


def test_chat_switches_to_visit_mode_when_candidate_index_is_selected(
    make_finder, runner_module, monkeypatch, make_assessment, make_reply, make_hospital
):
    finder = make_finder()
    finder.last_reply = make_reply(
        hospitals=[make_hospital(hpid="H1"), make_hospital(hpid="H2")]
    )
    finder.classifier.assess.return_value = make_assessment(blocked=False)
    monkeypatch.setattr(runner_module, "selected_index", lambda text: 1)

    finder.chat("2번으로 갈게요")

    assert finder.mode == "visit"
    finder.visit.prepare.assert_called_once()
    (hospital, symptom_text), _ = finder.visit.prepare.call_args
    assert hospital.hpid == "H2"


def test_chat_raises_when_selected_index_out_of_range(
    make_finder, runner_module, monkeypatch, make_assessment, make_reply, make_hospital
):
    finder = make_finder()
    finder.last_reply = make_reply(hospitals=[make_hospital(hpid="H1")])
    finder.classifier.assess.return_value = make_assessment(blocked=False)
    monkeypatch.setattr(runner_module, "selected_index", lambda text: 5)

    with pytest.raises(ValueError):
        finder.chat("6번이요")


def test_chat_ignores_selection_when_assessment_blocked(
    make_finder, runner_module, monkeypatch, make_assessment, make_reply, make_hospital
):
    finder = make_finder()
    finder.last_reply = make_reply(hospitals=[make_hospital(hpid="H1")])
    finder.classifier.assess.return_value = make_assessment(blocked=True)
    monkeypatch.setattr(runner_module, "selected_index", lambda text: 0)

    finder.chat("1번이요")

    assert finder.mode == "search"
    finder.visit.prepare.assert_not_called()
    finder.session.begin.assert_called_once()


def test_chat_runs_new_search_when_no_candidate_selected(
    make_finder, runner_module, monkeypatch, make_assessment
):
    finder = make_finder()
    finder.classifier.assess.return_value = make_assessment()
    monkeypatch.setattr(runner_module, "selected_index", lambda text: None)

    finder.chat("강남역 근처 흉통")

    assert finder.mode == "search"
    finder.visit.reset.assert_called_once()
    finder.session.begin.assert_called_once()
    call_args, call_kwargs = finder.session.begin.call_args
    assert call_args[0] == "강남역 근처 흉통"
    assert call_kwargs["assessment"] is finder.classifier.assess.return_value


# ---------------------------------------------------------------------------
# _run_graph()
# ---------------------------------------------------------------------------


def test_run_graph_uses_structured_response_without_evidence_check(make_finder, make_reply):
    finder = make_finder()
    reply = make_reply()
    finder.graph.invoke.return_value = {"structured_response": reply}

    result = finder._run_graph(HumanMessage(content="hi"))

    assert result.reply is reply
    assert result.pending_approval is None
    finder.session.check_evidence.assert_not_called()


def test_run_graph_falls_back_to_make_reply_and_evidence_check_when_no_structured_response(
    make_finder, make_reply
):
    finder = make_finder()
    finder.graph.invoke.return_value = {}
    raw_reply = {"raw": True}
    finder.session.make_reply.return_value = raw_reply
    checked_reply = make_reply()
    finder.session.check_evidence.return_value = checked_reply

    result = finder._run_graph(HumanMessage(content="hi"))

    finder.session.check_evidence.assert_called_once_with(raw_reply)
    assert result.reply is checked_reply


def test_run_graph_marks_pending_and_returns_pending_approval_on_interrupt(
    make_finder, make_reply
):
    finder = make_finder()
    reply = make_reply()
    finder.graph.invoke.return_value = {"structured_response": reply, "__interrupt__": ["paused"]}
    finder.visit.pending = {"hpid": "H1", "name": "서울병원"}

    result = finder._run_graph(HumanMessage(content="hi"))

    assert finder.pending is True
    assert result.pending_approval == {"hpid": "H1", "name": "서울병원"}


def test_run_graph_falls_back_gracefully_when_graph_invoke_raises(make_finder, make_reply):
    finder = make_finder()
    finder.graph.invoke.side_effect = RuntimeError("boom")
    fallback_reply = make_reply()
    finder.session.make_reply.return_value = fallback_reply

    result = finder._run_graph(HumanMessage(content="hi"))

    assert finder.pending is False
    assert result.reply is fallback_reply
    assert result.note == "요청 처리에 실패하여 기본 확인 정보만 표시합니다."


# ---------------------------------------------------------------------------
# approve()
# ---------------------------------------------------------------------------


def test_approve_raises_when_nothing_pending(make_finder):
    finder = make_finder()
    finder.pending = False

    with pytest.raises(ValueError):
        finder.approve(True)


def test_approve_true_sends_approve_decision_and_clears_pending(make_finder, make_reply):
    finder = make_finder()
    finder.pending = True
    finder.graph.invoke.return_value = {"structured_response": make_reply()}

    finder.approve(True)

    assert finder.visit.approved is True
    assert finder.visit.decided is True
    assert finder.pending is False
    args, _ = finder.graph.invoke.call_args
    assert args[0] == {"decisions": [{"type": "approve"}]}


def test_approve_false_sends_reject_decision_with_message(make_finder, make_reply):
    finder = make_finder()
    finder.pending = True
    finder.graph.invoke.return_value = {"structured_response": make_reply()}

    finder.approve(False)

    assert finder.visit.approved is False
    args, _ = finder.graph.invoke.call_args
    assert args[0] == {
        "decisions": [{"type": "reject", "message": "사용자가 저장을 거절했습니다."}]
    }


# ---------------------------------------------------------------------------
# end_session() / close()
# ---------------------------------------------------------------------------


def test_end_session_resets_state_and_calls_clear_session(make_finder, runner_module, make_reply):
    finder = make_finder()
    finder.pending = True
    finder.mode = "visit"
    finder.last_reply = make_reply()

    finder.end_session()

    runner_module.clear_session.assert_called_once_with(
        finder.session, finder.checkpointer, finder.context.user_id
    )
    finder.visit.reset.assert_called_once()
    assert finder.pending is False
    assert finder.mode == "search"
    assert finder.last_reply is None


def test_close_ends_session_and_closes_provider(make_finder):
    finder = make_finder()

    finder.close()

    finder.session.provider.close.assert_called_once()
