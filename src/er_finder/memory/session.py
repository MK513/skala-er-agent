"""세션 관리 — 체크포인터 연결, 세션 초기화/종료.

설계서 §1.5(기술): "대화 상태는 InMemorySaver(thread_id=user_id)".
설계서 §1.5(보안): "사용자 위치는 세션 종료 시 폐기한다. Store에는 사용자가 동의한 기본 주소와 방문 기록만 저장한다."

이 모듈은 State(대화 체크포인트)의 생명주기만 다룬다. Store(home_address,recent_visits)는 
세션과 무관하게 영속되므로 여기서 건드리지 않는다 
세션을 초기화/삭제해도 Store 데이터는 그대로 남는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver


@dataclass
class SessionManager:
    """thread_id=user_id로 체크포인터를 다루는 얇은 래퍼."""

    checkpointer: InMemorySaver

    def build_config(self, user_id: str) -> RunnableConfig:
        """create_agent.invoke(...) / .stream(...)에 넘길 config를 만든다.

        thread_id를 user_id로 고정해서, 같은 user_id로 다시 호출하면
        InMemorySaver가 이전 대화 체크포인트를 이어서 읽어오게 한다.
        조원1의 runner.py는 매 호출마다 이 config를 직접 조립하지 않고
        여기를 거쳐야, thread_id 규칙이 한 곳(session.py)에서만 관리된다.
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id는 빈 값일 수 없습니다.")
        return {"configurable": {"thread_id": user_id}}

    def has_active_session(self, user_id: str) -> bool:
        """이 user_id로 저장된 체크포인트(대화 상태)가 있는지 확인한다."""
        config = self.build_config(user_id)
        return self.checkpointer.get_tuple(config) is not None

    def reset_session(self, user_id: str) -> None:
        """대화 상태(State 체크포인트)를 완전히 지우고 새 대화로 만든다.

        사용자가 "새로 시작"을 요청했을 때(cli/commands.py의 초기화 명령)
        호출된다. current_location, triage, candidates 등 State에 있던
        모든 값이 함께 사라진다 — Store(home_address, recent_visits)는
        건드리지 않으므로 그대로 남는다. 존재하지 않는 thread_id를 넘겨도
        에러 없이 조용히 넘어간다(이미 세션이 없는 상태와 동일하게 취급).
        """
        self.checkpointer.delete_thread(user_id)

    def end_session(self, user_id: str) -> None:
        """세션 종료 시 호출한다. 보안 규칙에 따라 위치 등 State를 폐기한다.

        현재 구현은 reset_session과 동일하게 체크포인트를 완전히 지운다.
        메서드를 별도로 둔 이유는, "대화 초기화"(사용자가 능동적으로 요청)와
        "세션 종료"(앱이 자동으로 정리, 예: 타임아웃)가 나중에 서로 다른
        부가 동작(로그 기록 등)을 가질 수 있어서다. 지금은 둘 다 완전
        삭제라는 점에서 동일하게 처리한다.
        """
        self.checkpointer.delete_thread(user_id)
