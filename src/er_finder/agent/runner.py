from dataclasses import dataclass

from langchain_core.messages import HumanMessage
from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    PIIMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.structured_output import ToolStrategy

from er_finder.cli.renderer import render_reply
from er_finder.agent.prompts import SYSTEM_PROMPT
from er_finder.agent.tools import TOOLS
from er_finder.guardrails.middleware import (
    EmergencyInputGuard,
    EvidenceCheckMiddleware,
    ProfileDynamicPrompt,
)
from er_finder.guardrails.pii import PII_PATTERN
from er_finder.guardrails.triage import InputClassifier
from er_finder.memory.context import RuntimeContext
from er_finder.memory.session import clear_session, make_checkpointer
from er_finder.memory.state import ERGraphState
from er_finder.memory.store import Profiles
from er_finder.memory.visit_plan import VisitPlan, selected_index
from er_finder.models import EMERGENCY, ERSearchReply
from er_finder.safety import mask_pii, safe_data
from er_finder.search.service import SearchSession


@dataclass
class ChatResult:
    """chat()/approve() 한 턴 처리 결과를 담는 컨테이너.

    reply는 항상 채워지지만(그래프 실패 시 session.make_reply()로 폴백),
    pending_approval은 HITL 인터럽트(save_visit_plan 승인 대기) 중일 때만
    값이 있고 그 외에는 None이다. note는 트리아지 사유 또는 방문 이력
    안내처럼 있을 수도 없을 수도 있는 부가 설명이라 Optional로 둔다.
    """

    reply: ERSearchReply
    text: str
    pending_approval: dict | None = None
    note: str | None = None

class ERFinder:
    def __init__(
        self,
        provider,
        model=None,
        classifier=None,
        user_id="local-user",
        transport="car",
        store=None,
        checkpointer=None,
        on_emergency=None,
    ):
        """세션 하나에 필요한 협력 객체를 만들고 LangGraph 에이전트를 조립한다.

        model/classifier/store/checkpointer/on_emergency를 전부 선택 인자로
        둔 것은 테스트나 다른 진입점에서 목(mock) 객체를 주입할 수 있게
        하기 위함이다(예: tests/unit/agent/conftest.py의 make_finder).
        미들웨어 리스트의 순서와 각 항목 뒤 주석(before_agent/before_model/
        wrap_model_call/wrap_tool_call/after_model/after_agent)은 LangGraph
        훅 단계를 그대로 표기한 것으로, 순서를 바꾸면 실행 시점이 달라지므로
        임의로 재배열하지 않는다.
        """
        self.context = RuntimeContext(user_id, transport)
        self.session = SearchSession(provider, transport)
        self.profiles = Profiles(user_id, store)
        self.visit = VisitPlan(self.profiles, self.session.now)

        self.checkpointer = checkpointer or make_checkpointer()
        self.classifier = classifier or InputClassifier()
        self.on_emergency = on_emergency
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
                EmergencyInputGuard(self.session),  # before_agent
                ProfileDynamicPrompt(self.session, self.profiles, self.visit),  # before_model
                PIIMiddleware("korean_personal_data", strategy="redact", detector=PII_PATTERN),  # before_model
                ModelCallLimitMiddleware(run_limit=10, exit_behavior="end"),  # wrap_model_call
                ToolRetryMiddleware(max_retries=2, initial_delay=1.0),  # wrap_tool_call
                HumanInTheLoopMiddleware(
                    interrupt_on={"save_visit_plan": {"allowed_decisions": ["approve", "reject"]}},
                    description_prefix="이 방문 계획을 저장할까요?",
                ),  # after_model
                EvidenceCheckMiddleware(self.session),  # after_agent
            ],
        )
        self.run_config = {"configurable": {"thread_id": user_id, "session": self.session}}
        self.last_reply = None
        self.pending = False
        self.mode = "search"

    def chat(self, text: str, *, force_refresh: bool = False) -> ChatResult:
        """사용자 발화 한 턴을 처리해 ChatResult를 돌려준다.

        여기서 하는 마스킹/트리아지/모드 분기는 모두 그래프를 호출하기 전
        애플리케이션 레벨의 전처리다. PIIMiddleware(러너 __init__에서 등록)는
        모델에 보내기 직전 단계에서 한 번 더 마스킹하므로, mask_pii()가
        이중 방어의 첫 번째 레이어라는 점에 유의한다.
        """
        # 1. PII 마스킹 및 기본 유효성 검사
        text = mask_pii(text).strip()
        if not text:
            raise ValueError("위치와 증상을 입력하세요.")

        # 2. 응급도 평가 (중복 제거: classifier 하나로 일원화)
        # EmergencyInputGuard 미들웨어와는 별개의 애플리케이션 레벨 체크다.
        # critical이면 그래프 실행 여부와 무관하게 즉시 on_emergency 콜백을 울린다.
        assessment = self.classifier.assess(text)
        if assessment.triage.severity == "critical" and self.on_emergency:
            self.on_emergency(EMERGENCY)

        # 3. 방문 이력 질의 확인
        # "지난번"/"최근 방문" 같은 표현은 별도 LLM 호출 없이 여기서 바로
        # 처리한다. safe_data()로 이력 데이터를 안전한 형태로 가공해
        # 노출하며, 응답 자체는 note로만 흘려보내고 병상/수용 여부는
        # 항상 새로 조회하라고 명시한다(캐시된 이력을 그대로 신뢰하지 않음).
        history_note = None
        if "지난번" in text or "최근 방문" in text:
            visits = self.profiles.recent_visits()
            history_note = (
                f"최근 저장한 방문 계획: {safe_data(visits[-1]['name'])}. 현재 수용 여부는 새로 확인해야 합니다."
                if visits else "저장된 방문 기록이 없습니다."
            )

        # 4. 후보 번호 선택(방문 모드) vs 일반 검색 분기
        # selected_index()가 텍스트에서 "1번", "2" 같은 후보 선택을 파싱한다.
        # assessment.blocked(트리아지에서 차단된 입력)일 때는 선택을 무시하고
        # 항상 일반 검색 분기로 보내 방문 확정을 막는다.
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
        return self._run_graph(HumanMessage(content=text), history_note)

    def approve(self, approved: bool) -> ChatResult:
        """방문 계획 저장 승인/거부 처리.

        HumanInTheLoopMiddleware가 save_visit_plan 도구 호출 직전에 그래프를
        인터럽트해둔 상태(self.pending=True)에서만 호출 가능하다. decision
        dict는 LangGraph의 HITL 재개(resume) 규약을 따르며, approve 여부에
        따라 {"type": "approve"} 또는 사유가 담긴 {"type": "reject", ...}를
        그래프에 되돌려 보내 인터럽트를 해제한다.
        """
        if not self.pending:
            raise ValueError("승인 대기 중인 방문 계획이 없습니다.")

        self.visit.approved = approved
        self.visit.decided = True
        self.pending = False

        decision = (
            {"type": "approve"}
            if approved
            else {"type": "reject", "message": "사용자가 저장을 거절했습니다."}
        )
        return self._run_graph({"decisions": [decision]})

    def _run_graph(self, inputs, history_note=None) -> ChatResult:
        """Graph 호출 및 결과 객체(ChatResult) 파싱 일원화.

        chat()과 approve() 양쪽에서 공유하는 유일한 그래프 진입점이다.
        structured_response가 비어 있거나(모델이 구조화 출력을 못 낸 경우)
        ERSearchReply가 아닌 경우 session.check_evidence()로 한 번 더
        검증/보정한다. 예외는 여기서 전부 삼키고 session.make_reply()가
        만드는 안전한 기본 응답으로 폴백한다 — 그래프 실행 중 어떤 예외가
        나더라도 사용자에게는 항상 유효한 ERSearchReply를 돌려주기 위함이다.
        """
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
            pending_approval=pending_data,
            note=note,
        )

    def end_session(self):
        """대화 스레드를 초기화해 다음 chat() 호출이 새 세션처럼 시작되게 한다.

        clear_session()이 checkpointer에 쌓인 LangGraph 체크포인트(스레드
        히스토리)를 지우고, 그 외 필드는 __init__ 시점의 초기값으로
        되돌린다. provider/session 객체 자체는 재사용하므로 새 ERFinder를
        만들 필요 없이 같은 인스턴스로 다음 사용자와의 대화를 이어갈 수 있다.
        """
        clear_session(self.session, self.checkpointer, self.context.user_id)
        self.visit.reset()
        self.pending = False
        self.mode = "search"
        self.last_reply = None

    def close(self):
        """세션을 종료하고 provider가 잡고 있는 외부 리소스(커넥션 등)를 닫는다.

        end_session()과 달리 인스턴스를 더 이상 재사용하지 않을 때, 즉
        ERFinder 자체를 폐기하는 시점에 호출한다.
        """
        self.end_session()
        self.session.provider.close()