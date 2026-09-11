import pytest

from er_finder.search.coordinates import extract_coordinates, parse_coordinates
from er_finder.search.service import SearchSession, extract_location
from er_finder.web.provider import LiveProvider


def test_coordinates_are_explicit_and_validated():
    assert parse_coordinates("37.497942, 127.027621") == (37.497942, 127.027621)
    assert parse_coordinates("강남구 역삼동") is None
    assert extract_coordinates("위치 (37.5, 127.0), 손가락이 부었어요") == "37.5, 127.0"
    assert extract_location("37.5, 127.0 손가락이 부었어요") == "37.5, 127.0"
    for invalid in ("91.0, 127.0", "37.5, 181.0", "-91.0, 0.0"):
        with pytest.raises(ValueError):
            parse_coordinates(invalid)


def test_direct_coordinates_never_call_kakao():
    class NoGeocoder:
        def geocode(self, query):
            pytest.fail("Direct coordinates must not call the address API")

    provider = LiveProvider(geocoder=NoGeocoder(), medical_client=object())
    result = provider.geocode("37.5, 127.0")
    assert result == {"found": True, "lat": 37.5, "lon": 127.0}
    session = SearchSession(provider)
    session.begin("37.5, 127.0, 손가락이 부었어요")
    session.geocode(session.location_query)
    assert session.next_calls()[0]["args"] == {"lat": 37.5, "lon": 127.0, "radius_km": 5}


def test_sejong_region_without_a_district_is_still_queried():
    session = SearchSession(object())
    session.facilities = {"H1": {"sido": "세종특별자치시", "sigungu": ""}}
    assert session.regions() == [{"sido": "세종특별자치시", "sigungu": ""}]
