"""Session-scoped State — 대화 중 계속 바뀌는 값.

세션(대화) 안에서만 유효하고, 세션이 끝나면 사라져도 되는 값들을 담는다.
LangChain 1.4 create_agent의 state_schema로 등록되어, 
도구·미들웨어가 매 turn 읽고 쓴다.

주의할 점 : candidates/triage의 상세 타입은 조원1이 models.py에 정의할
ERSearchReply / HospitalCandidate / TriageAssessment(Pydantic) 스키마와 최종적으로 맞춰야 한다. 
지금은 memory 모듈을 독립적으로 개발·테스트할 수 있도록 최소 TypedDict로 임시 정의해두고, 
models.py가 준비되면 그쪽 타입으로 교체(또는 alias)할 계획이다 
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, TypedDict


class Location(TypedDict):
    lat: float
    lon: float
    sido: str
    sigungu: str


class TriageState(TypedDict, total=False):
    severity: Literal["critical", "urgent", "standard"]
    condition: str | None
    injection: bool
    confidence: float


class HospitalCandidate(TypedDict, total=False):
    hpid: str
    name: str
    distance_km: float
    er_beds_available: int | None
    beds_updated_at: str | None
    accepts_condition: Literal["yes", "no", "unknown"]
    er_tel: str | None
    address: str
    is_cached: bool
    is_stale: bool


BED_CACHE_TTL_SECONDS = 60


@dataclass
class BedCacheEntry:
    """시도·시군구 한 조합에 대한 병상 조회 결과 캐시 1건."""

    beds: list[HospitalCandidate]
    fetched_at: float = field(default_factory=time.time)

    def is_expired(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return (now - self.fetched_at) > BED_CACHE_TTL_SECONDS


@dataclass
class ERFinderState:
    """대화(세션) 도중 계속 바뀌는 값의 모음.

    Context와 달리 매 turn 갱신되는 게 정상 동작이라 frozen을 걸지 않았다
    (mutable dataclass).
    """

    messages: list[dict] = field(default_factory=list)
    current_location: Location | None = None
    triage: TriageState | None = None
    search_radius_km: int = 5
    candidates: list[HospitalCandidate] = field(default_factory=list)
    bed_cache: dict[tuple[str, str], BedCacheEntry] = field(default_factory=dict)

    # ---------- bed_cache 헬퍼 (60초 TTL) ----------

    def get_cached_beds(self, sido: str, sigungu: str) -> list[HospitalCandidate] | None:
        """캐시가 있고 60초 이내면 그 값을, 없거나 만료됐으면 None을 반환한다."""
        entry = self.bed_cache.get((sido, sigungu))
        if entry is None or entry.is_expired():
            return None
        return entry.beds

    def set_cached_beds(self, sido: str, sigungu: str, beds: list[HospitalCandidate]) -> None:
        self.bed_cache[(sido, sigungu)] = BedCacheEntry(beds=beds)

    # ---------- 반경 확대 헬퍼 ----------

    def expand_radius(self, sequence: list[int]) -> bool:
        """search_radius_km을 sequence 상에서 현재값보다 큰 다음 단계로 넓힌다.

        sequence는 조원3 radius.py가 이동수단별로 정한 순서
        (예: car/transit=[5,10,20,30], walk=[3,10,20,30]).
        더 넓힐 단계가 없으면 False를 반환해, 상위 로직이 "반경 확대
        최대 3회" 종료 조건을 판단할 수 있게 한다.

        current값이 sequence에 정확히 들어있지 않은 경우(예: reset_location_scoped
        호출 없이 dataclass 기본값 5가 그대로 남아있는데 sequence가 walk용
        [3,10,20,30]인 경우)에도, "현재값보다 큰 첫 값"으로 이동하기 때문에
        반경이 줄어드는 일은 없다 — index 기반 비교(sequence.index)는 이
        상황에서 sequence[0]으로 되돌아가 반경이 줄어드는 버그가 있었다.
        """
        for candidate in sequence:
            if candidate > self.search_radius_km:
                self.search_radius_km = candidate
                return True
        return False

    # ---------- 위치 갱신 헬퍼 ----------

    def reset_location_scoped(self, *, initial_radius_km: int = 5) -> None:
        """위치가 새로 확정되면 이전 위치 기준으로 쌓인 값들을 초기화한다.

        current_location을 갱신하는 시점에 함께 호출: 이전 반경·후보·캐시를
        그대로 두면 엉뚱한 지역 데이터가 새 위치 결과에 섞여 들어갈 수 있다.

        initial_radius_km: 이동수단별 반경 시퀀스의 시작값(예: walk=3,
        car/transit=5). State는 Context(transport)를 모르므로 호출자
        (조원3 geocode/radius.py, Context.transport를 읽을 수 있는 쪽)가
        맞는 시작값을 넘겨줘야 한다. 넘기지 않으면 car/transit 기준
        기본값(5)으로 초기화된다.
        """
        self.search_radius_km = initial_radius_km
        self.candidates = []
        self.bed_cache = {}
