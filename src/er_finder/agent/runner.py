from langchain_core.messages import HumanMessage

from er_finder.agent.factory import build_graph
from er_finder.agent.result import ChatResult, build_chat_result, resolve_turn_outcome
from er_finder.guardrails.triage import InputClassifier
from er_finder.memory.context import RuntimeContext
from er_finder.memory.session import clear_session, make_checkpointer
from er_finder.memory.store import Profiles
from er_finder.memory.visit_plan import VisitPlan, selected_index
from er_finder.models import EMERGENCY
from er_finder.safety import mask_pii, safe_data
from er_finder.search.service import SearchSession


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
        """세션 협력 객체를 만들고 build_graph()로 에이전트 그래프를 조립해 보관한다."""
        self.context = RuntimeContext(user_id, transport)
        self.session = SearchSession(provider, transport)
        self.profiles = Profiles(user_id, store)
        self.visit = VisitPlan(self.profiles, self.session.now)

        self.checkpointer = checkpointer or make_checkpointer()
        self.classifier = classifier or InputClassifier()
        self.on_emergency = on_emergency
        self.graph, self.counter = build_graph(
            model,
            checkpointer=self.checkpointer,
            store=self.profiles.store,
            session=self.session,
            profiles=self.profiles,
            visit=self.visit,
        )
        self.run_config = {"configurable": {"thread_id": user_id, "session": self.session}}
        self.last_reply = None
        self.pending = False
        self.mode = "search"

    def chat(self, text: str, *, force_refresh: bool = False) -> ChatResult:
        """사용자 발화를 마스킹·트리아지·모드 분기까지 전처리한 뒤 그래프를 실행해 ChatResult를 반환한다."""
        # 1. PII 마스킹 및 기본 유효성 검사
        text = mask_pii(text).strip()
        if not text:
            raise ValueError("위치와 증상을 입력하세요.")

        # 2. 응급도 평가: critical이면 그래프 실행과 무관하게 on_emergency를 즉시 호출한다.
        assessment = self.classifier.assess(text)
        if assessment.triage.severity == "critical" and self.on_emergency:
            self.on_emergency(EMERGENCY)

        self.counter.calls = 0

        # 3. "지난번"/"최근 방문" 질의는 LLM 호출 없이 여기서 바로 note로 답한다.
        history_note = None
        if "지난번" in text or "최근 방문" in text:
            visits = self.profiles.recent_visits()
            history_note = (
                f"최근 저장한 방문 계획: {safe_data(visits[-1]['name'])}. 현재 수용 여부는 새로 확인해야 합니다."
                if visits else "저장된 방문 기록이 없습니다."
            )

        # 4. 후보 번호 선택(방문 모드) vs 일반 검색 분기. blocked 입력은 선택을 무시한다.
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
        """대기 중인 방문 계획 저장을 승인/거부해 그래프의 HITL 인터럽트를 해제하고 ChatResult를 반환한다."""
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
        """chat()/approve() 공용 그래프 진입점. resolve_turn_outcome()으로 상태를 갱신하고 ChatResult를 반환한다."""
        outcome = resolve_turn_outcome(
            self.graph, inputs, self.run_config, self.context, self.session, history_note
        )
        self.pending = outcome.pending
        self.last_reply = outcome.reply

        return build_chat_result(outcome, self.visit, self.counter.calls)

    def end_session(self):
        """체크포인트와 인스턴스 상태를 초기화해 다음 chat()이 새 세션처럼 시작되게 한다."""
        clear_session(self.session, self.checkpointer, self.context.user_id)
        self.visit.reset()
        self.pending = False
        self.mode = "search"
        self.last_reply = None

    def close(self):
        """세션을 종료하고 provider의 외부 리소스를 닫는다(ERFinder 자체를 폐기할 때 호출)."""
        self.end_session()
        self.session.provider.close()
