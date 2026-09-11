"""Tool schemas and delegates against real search, selection and memory implementations."""

import pytest
from langgraph.store.memory import InMemoryStore

from er_finder.agent.adapters import VisitSelection
from er_finder.agent.tools import (
    TOOLS,
    geocode,
    get_er_bed_status,
    get_er_detail,
    get_severe_acceptance,
    list_nearby_ers,
    save_visit_plan,
)
from er_finder.memory.store import ERFinderStore
from er_finder.search.service import SearchSession
from tests.unit.agent.conftest import OfflineProvider


@pytest.fixture
def setup():
    session = SearchSession(OfflineProvider())
    session.begin("강남구 역삼동 가슴이 답답하고 식은땀이 나요")
    profiles = ERFinderStore(InMemoryStore(), "tools-test")
    visit = VisitSelection(profiles, session)
    return session, profiles, visit, {"configurable": {"session": session, "visit": visit}}


def locate(session, config):
    geocode.invoke({"query": session.location_query}, config=config)
    list_nearby_ers.invoke(session.next_calls()[0]["args"], config=config)


def finish(session, config):
    tools = {item.name: item for item in TOOLS}
    for _ in range(20):
        calls = session.next_calls()
        if not calls:
            return session.make_reply()
        for call in calls:
            tools[call["name"]].invoke(call["args"], config=config)
    raise AssertionError("tool sequence did not finish")


def test_geocode_and_nearby_use_validated_coordinates(setup):
    session, _, _, config = setup
    located = geocode.invoke({"query": "강남구 역삼동"}, config=config)
    assert located["location"]["lat"] == 37.5
    with pytest.raises(ValueError):
        list_nearby_ers.invoke({"lat": 0, "lon": 0, "radius_km": 5}, config=config)
    listed = list_nearby_ers.invoke(session.next_calls()[0]["args"], config=config)
    assert listed["facilities"]


def test_bed_tool_accepts_actual_regions_contract_and_rejects_invented_hpid(setup):
    session, _, _, config = setup
    locate(session, config)
    args = session.next_calls()[0]["args"]
    assert "regions" in args
    with pytest.raises(ValueError):
        get_er_bed_status.invoke({**args, "hpids": ["FORGED"]}, config=config)
    result = get_er_bed_status.invoke(args, config=config)
    assert result["beds"] and session.beds_checked


def test_severe_tool_uses_regions_and_preserves_unknown_or_rejected_acceptance(setup):
    session, _, _, config = setup
    locate(session, config)
    get_er_bed_status.invoke(session.next_calls()[0]["args"], config=config)
    result = get_severe_acceptance.invoke(session.next_calls()[0]["args"], config=config)
    assert session.severe_checked
    assert any(item["acceptable"] is False for item in result["acceptance"])


def test_detail_requires_current_top_candidate(setup):
    session, _, _, config = setup
    with pytest.raises(ValueError):
        get_er_detail.invoke({"hpid": "FORGED"}, config=config)
    reply = finish(session, config)
    assert all(hospital.hpid in session.details for hospital in reply.hospitals)


def test_save_requires_explicit_approval_and_writes_once(setup):
    session, profiles, visit, config = setup
    reply = finish(session, config)
    visit.prepare(reply.hospitals[0], session.symptom_text)
    args = visit.pending
    with pytest.raises(ValueError):
        save_visit_plan.invoke(args, config=config)
    assert profiles.get_recent_visits() == []
    visit.authorize(True)
    result = save_visit_plan.invoke(args, config=config)
    assert result["saved"] and result["visit_id"]
    with pytest.raises(ValueError):
        save_visit_plan.invoke(args, config=config)
    assert len(profiles.get_recent_visits()) == 1


def test_save_rejects_forged_arguments_even_after_approval(setup):
    session, profiles, visit, config = setup
    reply = finish(session, config)
    visit.prepare(reply.hospitals[0], session.symptom_text)
    visit.authorize(True)
    with pytest.raises(ValueError):
        save_visit_plan.invoke({**visit.pending, "hpid": "FORGED"}, config=config)
    assert profiles.get_recent_visits() == []


def test_save_rejects_previous_search_selection(setup):
    session, profiles, visit, config = setup
    reply = finish(session, config)
    visit.prepare(reply.hospitals[0], session.symptom_text)
    visit.authorize(True)
    args = visit.pending
    session.begin("경포대 발목 통증")
    with pytest.raises(ValueError):
        save_visit_plan.invoke(args, config=config)
    assert profiles.get_recent_visits() == []
