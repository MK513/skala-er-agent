"""save_visit_plan 관련 로직 — HITL 승인 이후에만 Store에 쓴다.

설계서 §1.5(보안): "모든 도구는 읽기 전용이며, 유일한 쓰기 도구인
save_visit_plan은 HITL 승인 후에만 실행된다."
설계서 §2.5(Tool 설계) save_visit_plan: "승인 거절 시 실행하지 않음. 저장
실패 시 saved=False 반환, 재시도 안 함."

이 모듈은 HumanInTheLoopMiddleware(after_model)가 승인/거절 결정을 받은
'이후'에 호출되는 부분만 담당한다. 승인 요청을 사용자에게 띄우는 인터럽트
자체는 미들웨어(조원1의 agent 쪽) 책임이고, 여기서는 "승인됐으면 저장,
거절됐으면 저장 안 함"이라는 결정 이후의 흐름만 구현한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from er_finder.memory.store import ERFinderStore, VisitRecord


class VisitPlanStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class PendingVisitPlan:
    """승인 대기 중인 방문 계획 1건.

    save_visit_plan 도구가 호출되면 바로 Store에 쓰지 않고, 먼저 이 객체를
    만들어 HITL 인터럽트에 실어 보낸다. 사용자가 승인/거절하면 그 결과를
    가지고 decide()를 통해 이 객체의 상태를 한 번만 확정짓는다.
    """

    hpid: str
    name: str
    symptom_summary: str
    status: VisitPlanStatus = VisitPlanStatus.PENDING

    def __post_init__(self) -> None:
        if not self.hpid or not self.name:
            raise ValueError("hpid와 name은 필수입니다.")


@dataclass
class VisitPlanResult:
    """save_visit_plan 도구가 최종적으로 돌려주는 값.

    Tool 설계(§2.5)에서 정의한 반환 타입 dict(saved, visit_id)를 그대로 담는다.
    reason은 도구 반환값에는 포함하지 않고, 로그/디버깅용으로만 쓴다.
    """

    saved: bool
    visit_id: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict:
        """설계서 Tool 반환 타입: dict (saved, visit_id)."""
        return {"saved": self.saved, "visit_id": self.visit_id}


class VisitPlanService:
    """PendingVisitPlan의 승인/거절 이후 처리를 담당한다."""

    def __init__(self, store: ERFinderStore) -> None:
        self._store = store

    def decide(self, plan: PendingVisitPlan, *, approved: bool) -> VisitPlanResult:
        """승인/거절 결과를 받아 최종 저장 여부를 확정한다.

        이미 결정이 난 plan(PENDING이 아님)에 다시 decide()를 호출하면
        RuntimeError를 던진다. HITL 인터럽트는 정확히 한 번만 응답을 받는
        게 정상이므로, 같은 plan에 두 번째 decide 호출이 들어오는 것은
        버그이거나 재시도 로직이 잘못 걸린 신호로 본다 — 조용히 무시하면
        중복 저장/이중 판정 같은 버그를 늦게 발견하게 되므로 바로 터뜨린다.
        """
        if plan.status is not VisitPlanStatus.PENDING:
            raise RuntimeError(
                f"이미 결정된 방문 계획입니다 (status={plan.status.value}). "
                "재결정은 지원하지 않습니다."
            )

        if not approved:
            plan.status = VisitPlanStatus.REJECTED
            return VisitPlanResult(saved=False, reason="user_rejected")

        plan.status = VisitPlanStatus.APPROVED
        try:
            record: VisitRecord = self._store.add_visit(
                hpid=plan.hpid,
                name=plan.name,
                symptom_summary=plan.symptom_summary,
            )
        except Exception:
            # 설계서: "저장 실패 시 saved=False 반환, 재시도 안 함"
            return VisitPlanResult(saved=False, reason="store_write_failed")

        return VisitPlanResult(saved=True, visit_id=record["visit_id"])
