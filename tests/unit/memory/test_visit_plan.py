from __future__ import annotations

import pytest
from langgraph.store.memory import InMemoryStore

from er_finder.memory.store import ERFinderStore
from er_finder.memory.visit_plan import (
    PendingVisitPlan,
    VisitPlanService,
    VisitPlanStatus,
)


@pytest.fixture
def store():
    return ERFinderStore(InMemoryStore(), user_id="u123")


@pytest.fixture
def service(store):
    return VisitPlanService(store)


def test_pending_visit_plan_requires_hpid_and_name():
    with pytest.raises(ValueError):
        PendingVisitPlan(hpid="", name="A병원", symptom_summary="흉통")
    with pytest.raises(ValueError):
        PendingVisitPlan(hpid="A0001", name="", symptom_summary="흉통")


def test_pending_visit_plan_defaults_to_pending():
    plan = PendingVisitPlan(hpid="A0001", name="A병원", symptom_summary="흉통")
    assert plan.status is VisitPlanStatus.PENDING


def test_decide_approved_saves_to_store_and_updates_status(service, store):
    plan = PendingVisitPlan(hpid="A0001", name="A병원", symptom_summary="흉통")

    result = service.decide(plan, approved=True)

    assert result.saved is True
    assert result.visit_id is not None
    assert plan.status is VisitPlanStatus.APPROVED
    assert len(store.get_recent_visits()) == 1
    assert store.get_recent_visits()[0]["hpid"] == "A0001"


def test_decide_rejected_does_not_touch_store(service, store):
    plan = PendingVisitPlan(hpid="A0001", name="A병원", symptom_summary="흉통")

    result = service.decide(plan, approved=False)

    assert result.saved is False
    assert result.reason == "user_rejected"
    assert plan.status is VisitPlanStatus.REJECTED
    assert store.get_recent_visits() == []


def test_decide_twice_raises_runtime_error(service):
    plan = PendingVisitPlan(hpid="A0001", name="A병원", symptom_summary="흉통")
    service.decide(plan, approved=True)

    with pytest.raises(RuntimeError):
        service.decide(plan, approved=True)


def test_decide_when_store_write_fails_returns_saved_false_without_raising():
    class BrokenStore:
        def add_visit(self, **kwargs):
            raise ConnectionError("store down")

    service = VisitPlanService(BrokenStore())
    plan = PendingVisitPlan(hpid="A0001", name="A병원", symptom_summary="흉통")

    result = service.decide(plan, approved=True)

    assert result.saved is False
    assert result.reason == "store_write_failed"
    assert result.visit_id is None


def test_visit_plan_result_as_dict_only_exposes_saved_and_visit_id(service):
    plan = PendingVisitPlan(hpid="A0001", name="A병원", symptom_summary="흉통")
    result = service.decide(plan, approved=True)

    payload = result.as_dict()

    assert set(payload.keys()) == {"saved", "visit_id"}
    assert payload["saved"] is True
