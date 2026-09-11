"""Runtime Context — 대화 호출 시 한 번 정해지고 끝까지 바뀌지 않는 값.

설계서 §3.1 Context 표 중 Runtime Context 2개 항목(user_id, transport)을 담는다.
LangChain 1.4 create_agent의 context_schema로 등록되어, 
미들웨어·도구가 runtime.context로 읽기 전용 접근한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

TransportMode = Literal["walk", "car", "transit"]
_VALID_TRANSPORT_MODES = get_args(TransportMode)


@dataclass(frozen=True)
class ERFinderContext:
    """앱이 에이전트를 호출할 때 1회 전달하는 고정값.

    frozen=True로 불변을 강제한다. Context는 대화 도중 값이 바뀌면 안 되는
    항목이라, 실수로 재할당하려는 코드가 있으면 여기서 바로 에러가 나게 만들어
    State/Context 경계가 무너지는 걸 방지한다.
    """

    user_id: str
    """사용자 식별자. save_visit_plan 호출 시 Store 키로 사용하고,
    InMemorySaver(thread_id=user_id)로 세션 체크포인터 키로도 쓴다."""

    transport: TransportMode = "car"
    """이동수단. 기본값은 car.
    ProfileDynamicPrompt가 system prompt에 주입하고,
    list_nearby_ers/radius.py가 반경 확대 시작값과 순서를 결정하는 데 쓴다.
    - walk: 3 → 6 → 9 → 12km
    - car / transit: 5 → 10 → 20 → 30km
    """

    def __post_init__(self) -> None:
        if not self.user_id or not self.user_id.strip():
            raise ValueError("user_id는 빈 값일 수 없습니다 (Store/세션 키로 사용됨)")
        if self.transport not in _VALID_TRANSPORT_MODES:
            # Literal["walk","car","transit"]은 타입체커만 검사하고 런타임에는
            # 강제되지 않는다. transport는 반경 확대 시퀀스 선택 키로 쓰이므로
            # (radius.py), 앱 경계에서 잘못된 문자열이 그대로 들어오면 여기서 막는다.
            raise ValueError(
                f"transport는 {_VALID_TRANSPORT_MODES} 중 하나여야 합니다: "
                f"{self.transport!r}"
            )
