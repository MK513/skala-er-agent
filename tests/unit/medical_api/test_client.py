"""client.py 단위 테스트. respx로 실제 API 호출을 흉내내고 fixture를 응답으로 준다."""

import httpx
import pytest
import respx

from er_finder.medical_api import cache, client


def _url(endpoint: str) -> str:
    return client.BASE_URL.rstrip("/") + endpoint


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):
    """재시도 테스트가 실제로 몇 초씩 기다리지 않게 백오프를 0으로 만든다."""
    monkeypatch.setattr(client, "BACKOFF", 0)


@respx.mock
def test_list_nearby_ers_filters_by_radius_and_sorts(egen_fixture):
    respx.get(_url("/getEgytLcinfoInqire")).mock(
        return_value=httpx.Response(200, text=egen_fixture("nearby_gangnam.xml"))
    )

    rows = client.list_nearby_ers(37.497942, 127.027621, radius_km=2)

    assert len(rows) > 0
    assert all(row["distance_km"] <= 2 for row in rows)
    distances = [row["distance_km"] for row in rows]
    assert distances == sorted(distances)


@respx.mock
def test_get_er_bed_status_filters_by_hpids(egen_fixture):
    respx.get(_url("/getEmrrmRltmUsefulSckbdInfoInqire")).mock(
        return_value=httpx.Response(200, text=egen_fixture("bed_status_missing_values.xml"))
    )

    rows = client.get_er_bed_status("아무시도", "아무시군구", ["A9900001", "A9900003"])

    assert {row["hpid"] for row in rows} == {"A9900001", "A9900003"}


@respx.mock
def test_get_er_bed_status_falls_back_to_stale_cache_when_api_fails():
    respx.get(_url("/getEmrrmRltmUsefulSckbdInfoInqire")).mock(return_value=httpx.Response(500))

    bed_cache: dict = {}
    key = cache.make_key("시도", "시군구")
    cache.save(
        bed_cache,
        key,
        [{"hpid": "A1", "name": "병원A", "er_beds_available": 3, "beds_updated_at": None}],
    )
    bed_cache[key] = (bed_cache[key][0], 0)  # 저장 시각을 옛날로 만들어 강제로 만료시킴

    rows = client.get_er_bed_status("시도", "시군구", ["A1"], bed_cache)

    assert len(rows) == 1
    assert rows[0]["stale"] is True


@respx.mock
def test_get_severe_acceptance_combines_multiple_codes_with_or(egen_fixture):
    respx.get(_url("/getSrsillDissAceptncPosblInfoInqire")).mock(
        return_value=httpx.Response(200, text=egen_fixture("severe_gangnam.xml"))
    )

    rows = client.get_severe_acceptance("서울특별시", "강남구", "뇌출혈")  # mkioskty3 OR 4

    assert len(rows) > 0
    assert all(row["acceptable"] in (True, False, None) for row in rows)


@respx.mock
def test_get_severe_acceptance_unmapped_condition_skips_api_call():
    route = respx.get(_url("/getSrsillDissAceptncPosblInfoInqire"))

    rows = client.get_severe_acceptance("서울특별시", "강남구", "중증외상")  # Sprint 2

    assert rows == []
    assert route.call_count == 0


@respx.mock
def test_get_er_detail_real_fixture(egen_fixture):
    respx.get(_url("/getEgytBassInfoInqire")).mock(
        return_value=httpx.Response(200, text=egen_fixture("detail_A1100057.xml"))
    )

    detail = client.get_er_detail("A1100057")

    assert detail["name"]
    assert detail["er_tel"] == detail["main_tel"]


@respx.mock
def test_get_er_detail_returns_empty_dict_on_failure():
    respx.get(_url("/getEgytBassInfoInqire")).mock(return_value=httpx.Response(500))

    assert client.get_er_detail("없는병원") == {}
