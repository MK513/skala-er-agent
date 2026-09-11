"""세션 관리 — 체크포인터 연결, 세션 초기화/종료.

대화 상태는 InMemorySaver(thread_id=user_id)로 관리한다. 이 모듈은 State
(대화 체크포인트)의 생명주기만 다룬다. Store(home_address, recent_visits)는
세션과 무관하게 영속되므로, 세션을 초기화/삭제해도 그대로 남는다.
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
        InMemorySaver가 이전 대화를 이어서 읽어오게 한다.
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id는 빈 값일 수 없습니다.")
        return {"configurable": {"thread_id": user_id}}

    def has_active_session(self, user_id: str) -> bool:
        """이 user_id로 저장된 체크포인트(대화 상태)가 있는지 확인한다."""
        config = self.build_config(user_id)
        return self.checkpointer.get_tuple(config) is not None

    def reset_session(self, user_id: str) -> None:
        """대화 상태를 완전히 지우고 새 대화로 만든다.

        Store(home_address, recent_visits)는 건드리지 않으므로 그대로
        남는다. 존재하지 않는 thread_id를 넘겨도 에러 없이 넘어간다.
        """
        self.checkpointer.delete_thread(user_id)

    def end_session(self, user_id: str) -> None:
        """세션 종료 시 호출해 State를 폐기한다.

        지금은 reset_session과 동일하게 동작하지만, "사용자 요청에 의한
        초기화"와 "세션 종료"는 나중에 부가 동작이 달라질 수 있어 메서드를
        분리해뒀다.
        """
        self.checkpointer.delete_thread(user_id)
