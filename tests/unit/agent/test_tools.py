"""agent/tools.py 검증.

tools.py는 순수하게 config['configurable']['session']으로 호출을 위임만 하므로,
가짜 session 객체만 주면 실제 langchain 모델 호출 없이 전체 도구를 검증할 수 있다.
"""

from unittest.mock import MagicMock

from er_finder.agent.tools import (
    TOOLS,
    geocode,
    get_er_bed_status,
    get_er_detail,
    get_severe_acceptance,
    list_nearby_ers,
    save_visit_plan,
)


def _config(session):
    return {"configurable": {"session": session}}


def test_tools_registers_all_six_tools_in_call_order():
    names = [t.name for t in TOOLS]
    assert names == [
        "geocode",
        "list_nearby_ers",
        "get_er_bed_status",
        "get_severe_acceptance",
        "get_er_detail",
        "save_visit_plan",
    ]


def test_geocode_delegates_to_session_and_returns_its_result():
    session = MagicMock()
    session.geocode.return_value = {"lat": 37.5, "lon": 127.0, "found": True}

    result = geocode.invoke({"query": "강남역"}, config=_config(session))

    session.geocode.assert_called_once_with("강남역")
    assert result == {"lat": 37.5, "lon": 127.0, "found": True}


def test_list_nearby_ers_passes_coordinates_and_radius():
    session = MagicMock()
    session.list_nearby_ers.return_value = [{"hpid": "H1"}]

    result = list_nearby_ers.invoke(
        {"lat": 37.5, "lon": 127.0, "radius_km": 5}, config=_config(session)
    )

    session.list_nearby_ers.assert_called_once_with(37.5, 127.0, 5)
    assert result == [{"hpid": "H1"}]


def test_get_er_bed_status_passes_region_and_hpids():
    session = MagicMock()
    session.get_er_bed_status.return_value = [{"hpid": "H1", "er_beds_available": 3}]

    result = get_er_bed_status.invoke(
        {"sido": "서울", "sigungu": "강남구", "hpids": ["H1", "H2"]},
        config=_config(session),
    )

    session.get_er_bed_status.assert_called_once_with("서울", "강남구", ["H1", "H2"])
    assert result == [{"hpid": "H1", "er_beds_available": 3}]


def test_get_severe_acceptance_passes_condition():
    session = MagicMock()
    session.get_severe_acceptance.return_value = [{"hpid": "H1", "acceptable": True}]

    result = get_severe_acceptance.invoke(
        {"sido": "서울", "sigungu": "강남구", "condition": "심근경색"},
        config=_config(session),
    )

    session.get_severe_acceptance.assert_called_once_with("서울", "강남구", "심근경색")
    assert result == [{"hpid": "H1", "acceptable": True}]


def test_get_er_detail_passes_hpid():
    session = MagicMock()
    session.get_er_detail.return_value = {"name": "서울병원", "er_tel": "02-000-0000"}

    result = get_er_detail.invoke({"hpid": "H1"}, config=_config(session))

    session.get_er_detail.assert_called_once_with("H1")
    assert result == {"name": "서울병원", "er_tel": "02-000-0000"}


def test_save_visit_plan_passes_hpid_name_and_symptom_summary():
    session = MagicMock()
    session.save_visit_plan.return_value = {"saved": True, "visit_id": "V1"}

    result = save_visit_plan.invoke(
        {"hpid": "H1", "name": "서울병원", "symptom_summary": "흉통, 식은땀"},
        config=_config(session),
    )

    session.save_visit_plan.assert_called_once_with("H1", "서울병원", "흉통, 식은땀")
    assert result == {"saved": True, "visit_id": "V1"}
