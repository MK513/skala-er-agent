"""er_finder.memory — Context / State / Store / 세션 / 방문 계획 승인 로직 모음.

이 패키지는 응급실 찾기 에이전트가 다루는 세 가지 메모리 계층과,
그 위에서 동작하는 세션 관리·HITL 승인 흐름을 한데 묶어 노출한다.

- context.py    : Runtime Context (요청 1회, 불변) — ERFinderContext
- state.py      : Session State (대화 중, 매 turn 변함) — ERFinderState 등
- store.py      : Long-term Store (세션을 넘어 영속) — ERFinderStore 등
- session.py    : State(체크포인터)의 생명주기 관리 — SessionManager
- visit_plan.py : save_visit_plan의 HITL 승인 이후 처리 — VisitPlanService 등

다른 모듈에서는 개별 파일을 직접 import하지 않고
`from er_finder.memory import ERFinderContext, ERFinderState, ...`처럼
이 패키지에서 바로 가져다 쓴다.
"""

from __future__ import annotations

from er_finder.memory.context import ERFinderContext, TransportMode
from er_finder.memory.session import SessionManager
from er_finder.memory.state import (
    BED_CACHE_TTL_SECONDS,
    BedCacheEntry,
    ERFinderState,
    HospitalCandidate,
    Location,
    TriageState,
)
from er_finder.memory.store import (
    ConsentRequiredError,
    ERFinderStore,
    VisitRecord,
)
from er_finder.memory.visit_plan import (
    PendingVisitPlan,
    VisitPlanResult,
    VisitPlanService,
    VisitPlanStatus,
)

__all__ = [
    # context
    "ERFinderContext",
    "TransportMode",
    # session
    "SessionManager",
    # state
    "ERFinderState",
    "TriageState",
    "HospitalCandidate",
    "Location",
    "BedCacheEntry",
    "BED_CACHE_TTL_SECONDS",
    # store
    "ERFinderStore",
    "VisitRecord",
    "ConsentRequiredError",
    # visit_plan
    "PendingVisitPlan",
    "VisitPlanStatus",
    "VisitPlanResult",
    "VisitPlanService",
]