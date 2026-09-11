"""agent/runner.py(ERFinder) 검증.

conftest.py의 runner_module/make_finder 픽스처가 최소 스텁을 심어 runner.py만 독립적으로 돌린다.
LLM 모델은 어디에서도 호출하지 않는다 - create_agent 자체를 MagicMock으로 바꿔서
만든 가짜 그래프(finder.graph)의 invoke()만 호출되며, 그 반환값은 각 테스트가 직접 정한다.

테스트 개수를 적게 유지하기 위해 같은 메서드/시나리오 군(chat 분기, _run_graph 분기,
approve+세션 생명주기)을 하나의 테스트 함수 안에서 여러 finder 인스턴스로 검증한다.
"""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage


# ---------------------------------------------------------------------------
# chat()
# ---------------------------------------------------------------------------


# PII 마스킹 후 텍스트가 공백만 남으면 ValueError를 던지는지 확인한다.
def test_chat_raises_when_text_is_empty_after_masking(make_finder, runner_module, monkeypatch):
    finder = make_finder()
    monkeypatch.setattr(runner_module, "mask_pii", lambda text: "   ")

    with pytest.raises(ValueError):
        finder.chat("아무 의미 없는 입력")


# severity가 critical일 때만 on_emergency 콜백이 호출되고, standard면 호출되지 않는지 확인한다.
def test_chat_emergency_callback_only_for_critical_severity(
    make_finder, runner_module, monkeypatch, make_assessment
):
    monkeypatch.setattr(runner_module, "selected_index", lambda text: None)

    critical_callback = MagicMock()
    critical_finder = make_finder(on_emergency=critical_callback)
    critical_finder.classifier.assess.return_value = make_assessment(severity="critical")
    critical_finder.chat("의식이 없어요, 마포구 합정동")
    critical_callback.assert_called_once_with(runner_module.EMERGENCY)

    standard_callback = MagicMock()
    standard_finder = make_finder(on_emergency=standard_callback)
    standard_finder.classifier.assess.return_value = make_assessment(severity="standard")
    standard_finder.chat("발목을 삐었어요")
    standard_callback.assert_not_called()


# "지난번"/"최근 방문" 질의 시 저장된 방문이 있으면 그 이름을, 없으면 안내 문구를 note로 돌려주는지 확인한다.
def test_chat_history_note_reflects_recent_visits_or_absence(
    make_finder, runner_module, monkeypatch, make_assessment
):
    monkeypatch.setattr(runner_module, "selected_index", lambda text: None)

    with_visits = make_finder()
    with_visits.classifier.assess.return_value = make_assessment()
    with_visits.profiles.recent_visits.return_value = [{"name": "서울병원"}]
    result = with_visits.chat("지난번 병원 어디였지?")
    assert "서울병원" in result.note

    without_visits = make_finder()
    without_visits.classifier.assess.return_value = make_assessment()
    without_visits.profiles.recent_visits.return_value = []
    result = without_visits.chat("최근 방문 기록 알려줘")
    assert result.note == "저장된 방문 기록이 없습니다."


# 후보 선택 텍스트에 따라 visit 모드 전환/범위 초과 예외/blocked 시 무시/미선택 시 새 검색, 네 분기를 확인한다.
def test_chat_selection_flow_switches_mode_or_falls_back_to_search(
    make_finder, runner_module, monkeypatch, make_assessment, make_reply, make_hospital
):
    # 유효한 후보 번호를 선택하면 visit 모드로 전환된다.
    finder = make_finder()
    finder.last_reply = make_reply(
        hospitals=[make_hospital(hpid="H1"), make_hospital(hpid="H2")]
    )
    finder.classifier.assess.return_value = make_assessment(blocked=False)
    monkeypatch.setattr(runner_module, "selected_index", lambda text: 1)

    finder.chat("2번으로 갈게요")

    assert finder.mode == "visit"
    finder.visit.prepare.assert_called_once()
    (hospital, _symptom_text), _ = finder.visit.prepare.call_args
    assert hospital.hpid == "H2"

    # 범위를 벗어난 번호는 예외를 던진다.
    out_of_range_finder = make_finder()
    out_of_range_finder.last_reply = make_reply(hospitals=[make_hospital(hpid="H1")])
    out_of_range_finder.classifier.assess.return_value = make_assessment(blocked=False)
    monkeypatch.setattr(runner_module, "selected_index", lambda text: 5)
    with pytest.raises(ValueError):
        out_of_range_finder.chat("6번이요")

    # assessment가 blocked면 선택을 무시하고 일반 검색으로 보낸다.
    blocked_finder = make_finder()
    blocked_finder.last_reply = make_reply(hospitals=[make_hospital(hpid="H1")])
    blocked_finder.classifier.assess.return_value = make_assessment(blocked=True)
    monkeypatch.setattr(runner_module, "selected_index", lambda text: 0)
    blocked_finder.chat("1번이요")
    assert blocked_finder.mode == "search"
    blocked_finder.visit.prepare.assert_not_called()
    blocked_finder.session.begin.assert_called_once()

    # 후보 선택이 없으면 새 검색을 시작한다.
    search_finder = make_finder()
    search_finder.classifier.assess.return_value = make_assessment()
    monkeypatch.setattr(runner_module, "selected_index", lambda text: None)
    search_finder.chat("강남역 근처 흉통")
    assert search_finder.mode == "search"
    search_finder.visit.reset.assert_called_once()
    search_finder.session.begin.assert_called_once()
    call_args, call_kwargs = search_finder.session.begin.call_args
    assert call_args[0] == "강남역 근처 흉통"
    assert call_kwargs["assessment"] is search_finder.classifier.assess.return_value


# ---------------------------------------------------------------------------
# _run_graph()
# ---------------------------------------------------------------------------


# _run_graph()가 구조화 응답 사용/미응답 시 폴백+검증/인터럽트 시 pending/예외 시 폴백, 네 경로 모두 올바른 ChatResult를 만드는지 확인한다.
def test_run_graph_resolves_reply_across_structured_fallback_interrupt_and_exception(
    make_finder, make_reply
):
    # structured_response가 이미 ERSearchReply면 evidence check를 건너뛴다.
    direct_finder = make_finder()
    direct_reply = make_reply()
    direct_finder.graph.invoke.return_value = {"structured_response": direct_reply}
    result = direct_finder._run_graph(HumanMessage(content="hi"))
    assert result.reply is direct_reply
    assert result.pending_approval is None
    direct_finder.session.check_evidence.assert_not_called()

    # structured_response가 없으면 make_reply()로 만든 뒤 check_evidence로 보정한다.
    fallback_finder = make_finder()
    fallback_finder.graph.invoke.return_value = {}
    raw_reply = {"raw": True}
    fallback_finder.session.make_reply.return_value = raw_reply
    checked_reply = make_reply()
    fallback_finder.session.check_evidence.return_value = checked_reply
    result = fallback_finder._run_graph(HumanMessage(content="hi"))
    fallback_finder.session.check_evidence.assert_called_once_with(raw_reply)
    assert result.reply is checked_reply

    # 그래프가 인터럽트되면 pending 상태와 pending_approval을 채운다.
    interrupt_finder = make_finder()
    interrupt_reply = make_reply()
    interrupt_finder.graph.invoke.return_value = {
        "structured_response": interrupt_reply,
        "__interrupt__": ["paused"],
    }
    interrupt_finder.visit.pending = {"hpid": "H1", "name": "서울병원"}
    result = interrupt_finder._run_graph(HumanMessage(content="hi"))
    assert interrupt_finder.pending is True
    assert result.pending_approval == {"hpid": "H1", "name": "서울병원"}

    # 그래프 invoke가 예외를 던지면 기본 응답으로 안전하게 폴백한다.
    error_finder = make_finder()
    error_finder.graph.invoke.side_effect = RuntimeError("boom")
    fallback_reply = make_reply()
    error_finder.session.make_reply.return_value = fallback_reply
    result = error_finder._run_graph(HumanMessage(content="hi"))
    assert error_finder.pending is False
    assert result.reply is fallback_reply
    assert result.note == "요청 처리에 실패하여 기본 확인 정보만 표시합니다."


# ---------------------------------------------------------------------------
# approve() / end_session() / close()
# ---------------------------------------------------------------------------


# approve()의 대기 없음 예외/승인/거절 결정 전송과, end_session()/close()의 상태 초기화·정리를 확인한다.
def test_approve_flow_and_session_lifecycle(make_finder, runner_module, make_reply):
    # 승인 대기 중인 게 없으면 예외.
    idle_finder = make_finder()
    idle_finder.pending = False
    with pytest.raises(ValueError):
        idle_finder.approve(True)

    # 승인하면 approve 결정을 그래프에 보내고 pending을 해제한다.
    approve_finder = make_finder()
    approve_finder.pending = True
    approve_finder.graph.invoke.return_value = {"structured_response": make_reply()}
    approve_finder.approve(True)
    assert approve_finder.visit.approved is True
    assert approve_finder.visit.decided is True
    assert approve_finder.pending is False
    args, _ = approve_finder.graph.invoke.call_args
    assert args[0] == {"decisions": [{"type": "approve"}]}

    # 거절하면 사유가 담긴 reject 결정을 보낸다.
    reject_finder = make_finder()
    reject_finder.pending = True
    reject_finder.graph.invoke.return_value = {"structured_response": make_reply()}
    reject_finder.approve(False)
    assert reject_finder.visit.approved is False
    args, _ = reject_finder.graph.invoke.call_args
    assert args[0] == {
        "decisions": [{"type": "reject", "message": "사용자가 저장을 거절했습니다."}]
    }

    # end_session()은 checkpointer를 비우고 상태를 초기값으로 되돌린다.
    session_finder = make_finder()
    session_finder.pending = True
    session_finder.mode = "visit"
    session_finder.last_reply = make_reply()
    session_finder.end_session()
    runner_module.clear_session.assert_called_once_with(
        session_finder.session, session_finder.checkpointer, session_finder.context.user_id
    )
    session_finder.visit.reset.assert_called_once()
    assert session_finder.pending is False
    assert session_finder.mode == "search"
    assert session_finder.last_reply is None

    # close()는 end_session() 이후 provider까지 닫는다.
    close_finder = make_finder()
    close_finder.close()
    close_finder.session.provider.close.assert_called_once()
