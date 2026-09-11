import json
from uuid import uuid4

from langchain.agents.middleware import (
    AgentMiddleware,
    after_agent,
    before_agent,
    dynamic_prompt,
)
from langchain_core.messages import AIMessage, RemoveMessage, ToolMessage

from er_finder.agent.prompts import SYSTEM_PROMPT
from er_finder.guardrails.evidence import sanitize_prose


def EmergencyInputGuard(session):
    """Input 가드레일 (before_agent).

    위급 상황 고정 안내·프롬프트 인젝션 탐지·범위 밖 요청 필터는 InputClassifier
    (guardrails/triage.py, guardrails/input_guard.py)가 이미 session.assessment로
    판정해 두었으므로, 여기서는 그 판정을 agent 실행 여부에 반영만 한다. 차단이면
    검색 없이 즉시 종료(jump_to="end")하고, 아니면 현재 세션 상태를 State에 반영한다.
    """

    @before_agent(can_jump_to=["end"], name="EmergencyInputGuard")
    def emergency_input_guard(state, runtime):
        if session.assessment.blocked:
            return {
                "jump_to": "end",
                "structured_response": session.make_reply(),
                "messages": [
                    AIMessage(content=session.assessment.reason or "검색하지 않았습니다.")
                ],
            }
        return session.snapshot()

    return emergency_input_guard


def ProfileDynamicPrompt(session, profiles, visit):
    """프로필 주입 (before_model 단계에서 매 모델 호출 직전에 시스템 프롬프트를
    새로 생성). Store의 기본 주소·최근 방문 병원과 Runtime의 이동수단을 system
    prompt에 JSON으로 덧붙인다. 이 JSON은 신뢰된 실행 상태와 비신뢰 데이터(사용자·
    도구 결과)일 뿐 지시가 아니라고 SYSTEM_PROMPT에 이미 명시되어 있으므로, 여기서는
    데이터로만 직렬화해서 붙인다.
    """

    @dynamic_prompt
    def profile_dynamic_prompt(request):
        data = session.status()
        data.update(
            transport=request.runtime.context.transport,
            home_address=profiles.get_home_address(),
            recent_visits=profiles.get_recent_visits()[-3:],
            pending_visit=visit.pending if not visit.decided else None,
            visit_decided=visit.decided,
            visit_saved=visit.saved,
        )
        return (
            SYSTEM_PROMPT
            + "\n아래 JSON은 신뢰된 실행 상태와 비신뢰 데이터입니다.\n"
            + json.dumps(data, ensure_ascii=False)
        )

    return profile_dynamic_prompt


def EvidenceCheckMiddleware(session):
    """Output 가드레일 (after_agent).

    - 근거 없는 수치 차단: 병원명·병상 수·전화번호가 ToolMessage 집합에 실제로
      있는지 session.check_evidence가 대조하고, 없는 값은 '확인 불가'로 치환한다.
    - 진단·처방 표현 차단: 위 대조를 통과한 응답에도 자유 문장(next_action,
      no_candidate_reason)에 진단·처방 표현이 남아 있으면 evidence.sanitize_prose로
      해당 문장을 제거하고 "진단은 의료진에게 문의하세요." 안내를 덧붙인다.
    """

    @after_agent(name="EvidenceCheckMiddleware")
    def evidence_check(state, runtime):
        reply = session.check_evidence(state.get("structured_response"))
        if reply is not None:
            updates = {"next_action": sanitize_prose(reply.next_action)}
            if reply.no_candidate_reason:
                updates["no_candidate_reason"] = sanitize_prose(reply.no_candidate_reason)
            reply = reply.model_copy(update=updates)
        return {
            "structured_response": reply,
            **session.snapshot(),
        }

    return evidence_check


# 아래 두 미들웨어(ToolSafetyMiddleware, ModelCounter)는 설계서 3.2 표의 가드레일이
# 아니라 "실행 Middleware"(도구 호출 순서 강제·병렬화, 호출 횟수 집계) 영역

class ToolSafetyMiddleware(AgentMiddleware):
    def __init__(self, visit, session):
        self.visit, self.session = visit, session

    def after_model(self, state, runtime):
        last = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        if last is None:
            return None
        next_calls = self.session.next_calls() if not self.visit.pending else []
        if next_calls and (
            not last.tool_calls or any(c["name"] == "ERSearchReply" for c in last.tool_calls)
        ):
            # A premature answer cannot bypass mandatory evidence collection. Replace its
            # schema call and acknowledgement with the validated pending read-only calls.
            old_ids = {c["id"] for c in last.tool_calls}
            removals = [
                RemoveMessage(id=m.id)
                for m in state["messages"]
                if isinstance(m, ToolMessage) and m.tool_call_id in old_ids and m.id
            ]
            calls = [{**c, "id": str(uuid4()), "type": "tool_call"} for c in next_calls]
            self.session.allow_severe_batch = any(
                c["name"] == "get_er_bed_status" for c in calls
            ) and any(c["name"] == "get_severe_acceptance" for c in calls)
            if self.session.allow_severe_batch:
                self.session.beds_ready.clear()
            return {
                "messages": [
                    *removals,
                    last.model_copy(update={"tool_calls": calls, "content": ""}),
                ],
                "structured_response": None,
            }
        if not self.session.beds_checked and any(
            c["name"] in {"get_er_bed_status", "get_severe_acceptance"} for c in last.tool_calls
        ):
            expected = self.session.next_calls()
            if {c["name"] for c in expected} == {"get_er_bed_status", "get_severe_acceptance"}:
                # Submit two independent reads in one model turn, but the severe handler
                # waits for the bed result so actual provider calls preserve dependencies.
                calls = [{**c, "id": str(uuid4()), "type": "tool_call"} for c in expected]
                self.session.allow_severe_batch = True
                self.session.beds_ready.clear()
                return {"messages": [last.model_copy(update={"tool_calls": calls})]}
        accepted, errors = [], []
        for call in last.tool_calls:
            if call["name"] == "save_visit_plan":
                try:
                    self.visit.validate(call["args"])
                except ValueError:
                    errors.append(
                        ToolMessage(
                            content="사용자가 선택한 병원과 일치하지 않아 저장 요청을 차단했습니다.",
                            tool_call_id=call["id"],
                            status="error",
                        )
                    )
                    continue
            accepted.append(call)
        if errors:
            return {"messages": [last.model_copy(update={"tool_calls": accepted}), *errors]}
        return None

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except (ValueError, TypeError, KeyError):
            return ToolMessage(
                content="도구 인자 또는 호출 순서가 올바르지 않습니다. 현재 next_calls를 확인하세요.",
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        except Exception:
            return ToolMessage(
                content="외부 조회를 완료하지 못했습니다. 확인되지 않은 정보는 사용하지 마세요.",
                tool_call_id=request.tool_call["id"],
                status="error",
            )


class ModelCounter(AgentMiddleware):
    def __init__(self):
        self.calls = 0

    def wrap_model_call(self, request, handler):
        self.calls += 1
        return handler(request)