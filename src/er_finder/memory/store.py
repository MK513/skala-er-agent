"""Long-term memory (Store) — 세션이 끝나도 남아 다음 대화까지 이어지는 값.

설계서 §3.1의 Store 항목 2개(home_address, recent_visits)를 담당한다.
실제 저장소는 LangGraph의 InMemoryStore를 그대로 사용한다
(설계서 §1.5: "대화 상태는 InMemorySaver, 세션 간 프로필은 InMemoryStore에 둔다").

보안 규칙(§1.5): Store에는 "사용자가 동의한 기본 주소"와 "방문 기록"만
저장한다. current_location 같은 세션 중 위치 정보는 여기 들어오면 안 되고
State(state.py)에만 존재해야 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.store.base import BaseStore

_NAMESPACE_PROFILE = "profile"
_NAMESPACE_VISITS = "visits"
_HOME_ADDRESS_KEY = "home_address"


class VisitRecord(TypedDict):
    visit_id: str
    hpid: str
    name: str
    symptom_summary: str
    saved_at: str  # ISO 8601


class ConsentRequiredError(Exception):
    """동의 없이 home_address를 저장하려고 할 때 발생시키는 예외.

    설계서 §1.5 보안 항목: "Store에는 사용자가 동의한 기본 주소와 방문
    기록만 저장한다"를 코드 레벨에서 강제하기 위함이다.

    @dataclass로 만들면 Exception.__init__을 dataclass가 생성한 __init__이
    가려버려서 e.args가 항상 빈 튜플이 된다(피클링·구조화 로깅 도구가
    args를 참조할 때 메시지가 비어 보임). super().__init__(message)를
    직접 호출해 args가 정상적으로 채워지도록 한다.
    """

    def __init__(
        self, message: str = "사용자 동의 없이는 home_address를 저장할 수 없습니다."
    ) -> None:
        self.message = message
        super().__init__(message)


class ERFinderStore:
    """user_id별 home_address / recent_visits를 관리하는 얇은 래퍼.

    InMemoryStore를 직접 여기저기서 호출하지 않고 이 클래스를 거치게 해서,
    - namespace 규칙(("er_finder", user_id, ...))을 한 곳에서만 관리하고
    - "동의 없으면 저장 금지" 같은 규칙을 빼먹지 않게 만든다.
    """

    def __init__(self, store: BaseStore, user_id: str) -> None:
        self._store = store
        self._user_id = user_id

    # ---------- home_address ----------

    def get_home_address(self) -> str | None:
        item = self._store.get(self._profile_namespace(), _HOME_ADDRESS_KEY)
        if item is None:
            return None
        return item.value.get("address")

    def set_home_address(self, address: str, *, consent: bool) -> None:
        """기본 주소를 저장한다. consent=True인 경우에만 실제로 저장된다.

        Args:
            address: 저장할 주소 문자열.
            consent: 사용자가 저장에 동의했는지 여부. False면 저장하지 않고
                ConsentRequiredError를 던진다 — "동의 안 받고 저장"이라는
                실수를 코드가 조용히 통과시키지 않도록 한다.
        """
        if not consent:
            raise ConsentRequiredError()
        if not address or not address.strip():
            raise ValueError("address는 빈 값일 수 없습니다.")
        self._store.put(
            self._profile_namespace(),
            _HOME_ADDRESS_KEY,
            {"address": address, "saved_at": _now_iso()},
        )

    def clear_home_address(self) -> None:
        """사용자가 동의를 철회했을 때 기본 주소를 삭제한다."""
        self._store.delete(self._profile_namespace(), _HOME_ADDRESS_KEY)

    # ---------- recent_visits ----------

    def add_visit(self, *, hpid: str, name: str, symptom_summary: str) -> VisitRecord:
        """방문 계획을 저장한다.

        이 메서드는 HITL 승인이 이미 끝났다는 전제로 호출되어야 한다.
        승인 여부 판단 자체는 이 클래스의 책임이 아니라 visit_plan.py
        (5단계)의 책임이다 — Store는 "승인된 걸 기록하는 곳"이지
        "승인을 판단하는 곳"이 아니라는 역할 분리를 위해 나눴다.

        hpid/name 검증은 PendingVisitPlan.__post_init__에서도 하지만,
        VisitPlanService를 거치지 않고 이 메서드가 직접 호출되는 경로에서도
        빈 값이 조용히 저장되지 않도록 여기서도 한 번 더 막는다.
        """
        if not hpid or not hpid.strip():
            raise ValueError("hpid는 빈 값일 수 없습니다.")
        if not name or not name.strip():
            raise ValueError("name은 빈 값일 수 없습니다.")
        visit_id = str(uuid.uuid4())
        record: VisitRecord = {
            "visit_id": visit_id,
            "hpid": hpid,
            "name": name,
            "symptom_summary": symptom_summary,
            "saved_at": _now_iso(),
        }
        self._store.put(self._visits_namespace(), visit_id, dict(record))
        return record

    def get_recent_visits(self, limit: int = 5) -> list[VisitRecord]:
        """최근 방문 기록을 최신순으로 최대 limit개 반환한다.

        InMemoryStore.search()의 반환 순서는 저장 순서를 보장하지 않으므로,
        limit을 search() 호출 시점에 걸면 실제로는 최신이 아닌 임의의
        부분집합만 정렬 대상이 될 수 있다. 그래서 전체를 먼저 가져와
        saved_at 기준으로 정렬한 뒤에 limit을 적용한다.
        """
        items = self._store.search(self._visits_namespace())
        visits = [item.value for item in items]
        visits.sort(key=lambda v: v.get("saved_at", ""), reverse=True)
        return visits[:limit]

    # ---------- namespace 규칙 ----------

    def _profile_namespace(self) -> tuple[str, ...]:
        return ("er_finder", self._user_id, _NAMESPACE_PROFILE)

    def _visits_namespace(self) -> tuple[str, ...]:
        return ("er_finder", self._user_id, _NAMESPACE_VISITS)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
