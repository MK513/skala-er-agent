from dataclasses import dataclass

from langchain_core.messages import HumanMessage

from er_finder.cli.renderer import render_reply
from er_finder.agent.prompts import SYSTEM_PROMPT
from er_finder.agent.tools import TOOLS
from er_finder.guardrails.triage import InputClassifier
from er_finder.memory.context import RuntimeContext
from er_finder.memory.session import clear_session, make_checkpointer
from er_finder.memory.store import Profiles
from er_finder.memory.visit_plan import VisitPlan, selected_index
from er_finder.models import EMERGENCY, ERSearchReply
from er_finder.safety import mask_pii, safe_data
from er_finder.search.service import SearchSession

@dataclass
class ChatResult:
    reply: ERSearchReply
    text: str
    model_calls: int
    pending_approval: dict | None = None
    note: str | None = None

class ERFinder:
    def __init__(
        self,
        provider,
        model=None,
        classifier=None,
        *,
        user_id="local-user",
        transport="car",
        store=None,
        checkpointer=None,
        on_emergency=None,
    ):
        self.context = RuntimeContext(user_id, transport)
        self.session = SearchSession(provider, transport)
        self.profiles = Profiles(user_id, store)
        self.visit = VisitPlan(self.profiles, self.session.now)
        self.checkpointer = checkpointer or make_checkpointer()
        self.classifier = classifier or InputClassifier()
        self.on_emergency = on_emergency
        self.counter = ModelCounter()
        self.graph = create_agent(
            model,
            tools=TOOLS,
            system_prompt=SYSTEM_PROMPT,
            response_format=ToolStrategy(ERSearchReply, handle_errors=True),
            state_schema=ERGraphState,
            context_schema=RuntimeContext,
            checkpointer=self.checkpointer,
            store=self.profiles.store,
            middleware=[
                EvidenceCheckMiddleware(self.session),
                EmergencyInputGuard(self.session),
                ProfileDynamicPrompt(self.session, self.profiles, self.visit),
                PIIMiddleware("korean_personal_data", strategy="redact", detector=PII_PATTERN),
                ModelCallLimitMiddleware(run_limit=14, exit_behavior="end"),
                HumanInTheLoopMiddleware(
                    interrupt_on={"save_visit_plan": {"allowed_decisions": ["approve", "reject"]}},
                    description_prefix="이 방문 계획을 저장할까요?",
                ),
                ToolSafetyMiddleware(self.visit, self.session),
                self.counter,
            ],
        )
        self.run_config = {"configurable": {"thread_id": user_id}}
        self.last_reply = None
        self.pending = False
        self.mode = "search"

    def chat(self, text: str, *, force_refresh: bool = False) -> ChatResult:
        # 1. PII 마스킹 및 기본 유효성 검사
        text = mask_pii(text).strip()
        if not text:
            raise ValueError("위치와 증상을 입력하세요.")

        # 2. 응급도 평가 (중복 제거: classifier 하나로 일원화)
        assessment = self.classifier.assess(text)
        if assessment.triage.severity == "critical" and self.on_emergency:
            self.on_emergency(EMERGENCY)

        # 3. 방문 이력 질의 확인
        history_note = None
        if "지난번" in text or "최근 방문" in text:
            visits = self.profiles.recent_visits()
            history_note = (
                f"최근 저장한 방문 계획: {safe_data(visits[-1]['name'])}. 현재 수용 여부는 새로 확인해야 합니다."
                if visits else "저장된 방문 기록이 없습니다."
            )

        # 4. 후보 번호 선택(방문 모드) vs 일반 검색 분기
        selected = selected_index(text)
        if selected is not None and self.last_reply and not assessment.blocked:
            if selected >= len(self.last_reply.hospitals):
                raise ValueError("안내된 후보 번호를 선택하세요.")
            self.mode = "visit"
            self.visit.prepare(self.last_reply.hospitals[selected], self.session.symptom_text)
        else:
            self.mode = "search"
            self.visit.reset()
            self.session.begin(
                text,
                self.profiles.home_address(),
                force_refresh=force_refresh,
                assessment=assessment,
            )

        # 5. 에이전트 실행
        self.counter.calls = 0
        return self._run_graph(HumanMessage(content=text), history_note)

    def approve(self, approved: bool) -> ChatResult:
        """방문 계획 저장 승인/거부 처리"""
        if not self.pending:
            raise ValueError("승인 대기 중인 방문 계획이 없습니다.")
            
        self.visit.approved, self.visit.decided = approved, True
        self.pending = False

        decision = (
            {"type": "approve"}
            if approved
            else {"type": "reject", "message": "사용자가 저장을 거절했습니다."}
        )
        return self._run_graph({"decisions": [decision]})

    def _run_graph(self, inputs, history_note=None) -> ChatResult:
        """Graph 호출 및 결과 객체(ChatResult) 파싱 일원화"""
        try:
            output = self.graph.invoke(inputs, config=self.run_config, context=self.context)
            self.pending = bool(output.get("__interrupt__"))
            reply = output.get("structured_response") or self.session.make_reply()
            
            if not isinstance(reply, ERSearchReply):
                reply = self.session.check_evidence(reply)
                
            note = self.session.assessment.reason or history_note
        except Exception:
            self.pending = False
            reply = self.session.make_reply()
            note = "요청 처리에 실패하여 기본 확인 정보만 표시합니다."

        self.last_reply = reply
        pending_data = dict(self.visit.pending) if self.pending else None

        return ChatResult(
            reply=reply,
            text=render_reply(reply, note=note, pending=pending_data),
            model_calls=self.counter.calls,
            pending_approval=pending_data,
            note=note,
        )

    def end_session(self):
        clear_session(self.session, self.checkpointer, self.context.user_id)
        self.visit.reset()
        self.pending = False
        self.mode = "search"
        self.last_reply = None

    def close(self):
        self.end_session()
        self.session.provider.close()