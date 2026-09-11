from dataclasses import dataclass

from er_finder.cli.renderer import render_reply
from er_finder.models import ERSearchReply


@dataclass
class ChatResult:
    """chat()/approve() 한 턴의 최종 응답 묶음. pending_approval은 HITL 승인 대기 중에만 값이 있다."""

    reply: ERSearchReply
    text: str
    pending_approval: dict | None = None
    note: str | None = None


@dataclass
class TurnOutcome:
    """그래프 invoke 한 번의 결과(reply/note/인터럽트 여부)."""

    reply: ERSearchReply
    note: str | None
    pending: bool


def resolve_turn_outcome(graph, inputs, config, context, session, history_note=None) -> TurnOutcome:
    """그래프를 invoke해 TurnOutcome을 반환한다. 실패 시 session.make_reply() 기본 응답으로 폴백한다."""
    try:
        output = graph.invoke(inputs, config=config, context=context)
        pending = bool(output.get("__interrupt__"))
        reply = output.get("structured_response") or session.make_reply()

        if not isinstance(reply, ERSearchReply):
            reply = session.check_evidence(reply)

        note = session.assessment.reason or history_note

    except Exception:
        pending = False
        reply = session.make_reply()
        note = "요청 처리에 실패하여 기본 확인 정보만 표시합니다."

    return TurnOutcome(reply=reply, note=note, pending=pending)


def build_chat_result(outcome: TurnOutcome, visit) -> ChatResult:
    """TurnOutcome과 방문 계획 상태를 합쳐 ChatResult를 반환한다."""
    pending_data = dict(visit.pending) if outcome.pending else None

    return ChatResult(
        reply=outcome.reply,
        text=render_reply(outcome.reply, note=outcome.note, pending=pending_data),
        pending_approval=pending_data,
        note=outcome.note,
    )
