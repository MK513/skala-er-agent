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


# TOOLS 리스트에 6개 도구가 빠짐없이, 정해진 순서대로 등록됐는지 확인한다.
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


# 각 도구가 인자를 그대로 session의 동일 이름 메서드에 넘기고, 그 반환값을
# 그대로 돌려주는지 6개 도구 전부에 대해 한 번에 검증한다.
def test_each_tool_delegates_args_and_return_value_to_session():
    cases = [
        (geocode, "geocode", {"query": "강남역"}, ("강남역",), {"lat": 37.5, "lon": 127.0}),
        (
            list_nearby_ers,
            "list_nearby_ers",
            {"lat": 37.5, "lon": 127.0, "radius_km": 5},
            (37.5, 127.0, 5),
            [{"hpid": "H1"}],
        ),
        (
            get_er_bed_status,
            "get_er_bed_status",
            {"sido": "서울", "sigungu": "강남구", "hpids": ["H1", "H2"]},
            ("서울", "강남구", ["H1", "H2"]),
            [{"hpid": "H1", "er_beds_available": 3}],
        ),
        (
            get_severe_acceptance,
            "get_severe_acceptance",
            {"sido": "서울", "sigungu": "강남구", "condition": "심근경색"},
            ("서울", "강남구", "심근경색"),
            [{"hpid": "H1", "acceptable": True}],
        ),
        (
            get_er_detail,
            "get_er_detail",
            {"hpid": "H1"},
            ("H1",),
            {"name": "서울병원", "er_tel": "02-000-0000"},
        ),
        (
            save_visit_plan,
            "save_visit_plan",
            {"hpid": "H1", "name": "서울병원", "symptom_summary": "흉통, 식은땀"},
            ("H1", "서울병원", "흉통, 식은땀"),
            {"saved": True, "visit_id": "V1"},
        ),
    ]

    for tool, method_name, tool_input, expected_call_args, return_value in cases:
        session = MagicMock()
        getattr(session, method_name).return_value = return_value

        result = tool.invoke(tool_input, config=_config(session))

        getattr(session, method_name).assert_called_once_with(*expected_call_args)
        assert result == return_value, f"{method_name} returned unexpected result"
