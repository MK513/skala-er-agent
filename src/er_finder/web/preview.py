"""Fixed synthetic UI scenarios. No triage, geocoding, agent graph or external calls."""

from uuid import uuid4

from langgraph.store.memory import InMemoryStore

from er_finder.memory.store import ERFinderStore
from er_finder.memory.visit_plan import PendingVisitPlan, VisitPlanService
from er_finder.web.contracts import UIHospital, UIReply, WebResult

CASES = {
    "candidates": "후보 3곳 · 선택과 저장 승인",
    "location": "위치 재질문 · 다음 입력에서 후보 표시",
    "empty": "후보 없음 · 안내 표시",
    "critical": "119 우선 안내 · 위급 화면",
    "stale": "갱신 지연 · 장애 대체 데이터",
    "error": "서비스 오류 · 안전한 안내",
}
FIXTURE_TIMESTAMP = "2026-09-10T09:00:00+09:00"


class PreviewBackend:
    """Uses real member 4 consent/storage code, with scripted UI responses."""

    def __init__(self) -> None:
        self.user_id = str(uuid4())
        self.scenario = "candidates"
        self.profile = ERFinderStore(InMemoryStore(), self.user_id)
        self._plans = VisitPlanService(self.profile)
        self._reply: UIReply | None = None
        self._pending: PendingVisitPlan | None = None
        self._awaiting_location = False

    def chat(self, text: str, *, transport: str, force_refresh: bool = False) -> WebResult:
        if not force_refresh and self._reply and self._reply.hospitals:
            if "두 번째" in text and ("갈" in text or "선택" in text):
                return self.select_hospital(self._reply.hospitals[1].hpid)
        self._pending = None
        if self.scenario == "error":
            self._reply = None
            return WebResult(note="시연용 서비스 오류입니다. 잠시 후 다시 조회해 주세요.")

        # These are fixed display values, not member 3's search/radius policy.
        radius = 3 if transport == "walk" else 5
        reason = None
        hospitals: list[UIHospital] = []
        critical = self.scenario == "critical"
        next_action = "가상 후보를 선택해 방문 계획 저장 승인 화면을 확인하세요."
        if self.scenario == "location" and not self._awaiting_location:
            self._awaiting_location = True
            reason = "위치를 확인할 수 없습니다. 시연용 주소를 입력해 주세요."
            next_action = "다음 입력에서 고정된 합성 후보를 표시합니다."
        elif self.scenario in {"empty", "critical"}:
            radius = 30 if self.scenario == "empty" else radius
            reason = "이 시연 시나리오에는 확인된 후보가 없습니다."
            next_action = (
                "즉시 119에 연락하세요."
                if critical
                else "현재 수용 여부를 확인하지 못했습니다. 위급하면 119에 연락하세요."
            )
        else:
            hospitals = [
                UIHospital(
                    hpid=f"DEMO-00{index}",
                    name=f"가상 응급센터 {name}",
                    distance_km=distance,
                    er_beds_available=beds,
                    beds_updated_at=FIXTURE_TIMESTAMP,
                    address=f"시연 전용 주소 {index} (실제 기관 아님)",
                    # Fixed old fixture must never look like live/current data.
                    is_stale=True,
                    is_cached=self.scenario == "stale",
                )
                for index, name, distance, beds in [
                    (1, "A", 0.7, 4),
                    (2, "B", 1.2, 2),
                    (3, "C", 2.5, 5),
                ]
            ]
        self._reply = UIReply(
            severity="critical" if critical else "standard",
            call_119_first=critical,
            search_radius_km=radius,
            hospitals=hospitals,
            no_candidate_reason=reason,
            data_timestamp=FIXTURE_TIMESTAMP,
            next_action=next_action,
        )
        return WebResult(
            reply=self._reply,
            note="고정 합성 시나리오입니다. 입력 내용의 의료 분류는 수행하지 않습니다.",
        )

    def select_hospital(self, hpid: str) -> WebResult:
        hospital = (
            next((item for item in self._reply.hospitals if item.hpid == hpid), None)
            if self._reply
            else None
        )
        if hospital is None:
            return WebResult(reply=self._reply, note="현재 결과에 있는 후보만 선택할 수 있습니다.")
        self._pending = PendingVisitPlan(
            hpid=hospital.hpid,
            name=hospital.name,
            symptom_summary="화면 검증용 합성 방문 계획",
        )
        return WebResult(reply=self._reply, pending_approval=self._pending)

    def approve(self, approved: bool) -> WebResult:
        if self._pending is None:
            return WebResult(reply=self._reply, note="승인 대기 중인 방문 계획이 없습니다.")
        plan, self._pending = self._pending, None
        decision = self._plans.decide(plan, approved=approved)
        if decision.saved:
            note = "방문 계획을 저장했습니다. 병원 예약이나 연락은 실행하지 않았습니다."
        elif not approved:
            note = "저장을 거절했습니다. 방문 계획을 저장하지 않았습니다."
        else:
            note = "방문 계획을 저장하지 못했습니다. 다시 선택해 주세요."
        return WebResult(reply=self._reply, note=note)

    def reset(self) -> None:
        self._reply = None
        self._pending = None
        self._awaiting_location = False

    def forget(self) -> None:
        # This backend owns an entire private store. Drop it, never inspect private namespaces.
        self.reset()
        self.user_id = str(uuid4())
        self.profile = ERFinderStore(InMemoryStore(), self.user_id)
        self._plans = VisitPlanService(self.profile)
