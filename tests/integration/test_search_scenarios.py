"""Replay recorded E-Gen XML through real clients, parsing and search orchestration.

HTTP alone is replaced by MockTransport. Inputs and unrecorded empty responses
are synthetic, as declared by the scenario file; these are not clinical outcomes
or evidence of current hospital availability. No live requests or LLM calls run.
"""

import json
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import httpx
import pytest

from er_finder.medical_api import client as medical_client
from er_finder.search.distance import distance_km
from er_finder.search.geocoder import KakaoGeocoder
from er_finder.search.service import SearchSession
from er_finder.web.provider import LiveProvider

FIXTURES = Path(__file__).parents[1] / "fixtures"
SCENARIOS = json.loads((FIXTURES / "scenarios/sample_scenario.json").read_text(encoding="utf-8"))


def read_xml(name):
    return (FIXTURES / "egen" / name).read_text(encoding="utf-8")


@pytest.fixture
def replay_provider(monkeypatch):
    clients = []
    providers = []

    def create(case, *, nearby_status=200, empty_nearby=False):
        calls = []

        def handler(request):
            endpoint = request.url.path.rsplit("/", 1)[-1]
            region = [request.url.params.get("STAGE1"), request.url.params.get("STAGE2")]
            hpid = request.url.params.get("HPID")
            assert request.url.params["serviceKey"] == "offline-scenario-key"
            filename = SCENARIOS["unrecorded_response"]
            if endpoint == "getEgytLcinfoInqire":
                lat, lon = map(float, case["coordinates"].split(","))
                assert float(request.url.params["WGS84_LAT"]) == lat
                assert float(request.url.params["WGS84_LON"]) == lon
                filename = filename if empty_nearby else case["nearby"]
                status = nearby_status
            elif endpoint == "getEmrrmRltmUsefulSckbdInfoInqire":
                filename = case["beds"] if region == case["region"] else filename
                status = 200
            elif endpoint == "getSrsillDissAceptncPosblInfoInqire":
                filename = case["severe"] if region == case["region"] else filename
                status = 200
            elif endpoint == "getEgytBassInfoInqire":
                recorded = f"detail_{hpid}.xml"
                filename = recorded if (FIXTURES / "egen" / recorded).is_file() else filename
                status = 200
            else:
                raise AssertionError(f"Unmapped fixture endpoint: {endpoint}")
            calls.append(dict(endpoint=endpoint, region=region, hpid=hpid, fixture=filename))
            return httpx.Response(status, text=read_xml(filename))

        transport_client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(transport_client)
        monkeypatch.setattr(httpx, "request", transport_client.request)
        monkeypatch.setattr(medical_client, "SERVICE_KEY", "offline-scenario-key")
        monkeypatch.setattr(medical_client, "BASE_URL", "https://egen.fixture.local/service")
        monkeypatch.setattr(medical_client, "MAX_RETRIES", 0)

        def unexpected_geocode(_request):
            pytest.fail("Explicit coordinates must not call Kakao")

        kakao_client = httpx.Client(transport=httpx.MockTransport(unexpected_geocode))
        clients.append(kakao_client)
        geocoder = KakaoGeocoder(kakao_key="offline-kakao-key", client=kakao_client)
        provider = LiveProvider(geocoder=geocoder, medical_client=medical_client)
        providers.append(provider)
        return provider, calls

    yield create
    for provider in providers:
        provider.close()
    for client in clients:
        client.close()


@pytest.mark.parametrize("case", SCENARIOS["cases"], ids=lambda case: case["id"])
def test_recorded_search_scenarios_preserve_evidence_radius_and_order(case, replay_provider):
    provider, http_calls = replay_provider(case)
    session = SearchSession(provider, now=lambda: datetime.fromisoformat(SCENARIOS["now"]))
    session.begin(f"{case['coordinates']} {SCENARIOS['symptom_text']}")
    for _ in range(20):
        calls = session.next_calls()
        if not calls:
            break
        # Invoke the server-authorized batch in dependency order; actual parallel
        # graph dispatch is covered by the middleware and runner graph regressions.
        for call in calls:
            getattr(session, call["name"])(**call["args"])
    else:
        pytest.fail("Search did not terminate within the bounded fixture traversal")

    reply = session.check_evidence(None)
    assert len(reply.hospitals) <= 3
    assert [hospital.hpid for hospital in reply.hospitals] == case["expected_candidate_ids"]
    assert [
        entry["radius_km"] for entry in session.audit if entry["name"] == "list_nearby_ers"
    ] == case["expected_radii"]
    assert session.lookup_error is None
    if "expected_reason_contains" in case:
        assert case["expected_reason_contains"] in reply.no_candidate_reason

    source = ElementTree.fromstring(read_xml(case["nearby"]))
    facilities = {row.findtext("hpid"): row for row in source.findall(".//item")}
    bed_source = ElementTree.fromstring(read_xml(case["beds"]))
    beds = {row.findtext("hpid"): row for row in bed_source.findall(".//item")}
    severe_source = ElementTree.fromstring(read_xml(case["severe"]))
    severe = {row.findtext("hpid"): row for row in severe_source.findall(".//item")}
    assert {h.hpid for h in reply.hospitals} <= facilities.keys() & beds.keys() & severe.keys()
    distances = []
    for hospital in reply.hospitals:
        row = facilities[hospital.hpid]
        actual_distance = distance_km(
            session.location["lat"],
            session.location["lon"],
            float(row.findtext("latitude")),
            float(row.findtext("longitude")),
        )
        assert actual_distance <= reply.search_radius_km
        assert hospital.distance_km == round(actual_distance, 1)
        assert hospital.name == row.findtext("dutyName")
        assert hospital.er_beds_available == int(beds[hospital.hpid].findtext("hvec")) > 0
        assert severe[hospital.hpid].findtext("MKioskTy1").strip() == "Y"
        assert hospital.accepts_condition == "yes"
        assert datetime.fromisoformat(hospital.beds_updated_at).tzinfo is not None
        distances.append(hospital.distance_km)
    assert distances == sorted(distances)

    checked_regions = set()
    for call in http_calls:
        if call["endpoint"] == "getEmrrmRltmUsefulSckbdInfoInqire":
            checked_regions.add(tuple(call["region"]))
        elif call["endpoint"] == "getSrsillDissAceptncPosblInfoInqire":
            assert tuple(call["region"]) in checked_regions
    assert case["beds"] in {call["fixture"] for call in http_calls}
    assert case["severe"] in {call["fixture"] for call in http_calls}


def test_strict_live_provider_distinguishes_http_failure_from_successful_empty_xml(replay_provider):
    case = SCENARIOS["cases"][0]
    lat, lon = map(float, case["coordinates"].split(","))
    provider, calls = replay_provider(case, nearby_status=500)
    with pytest.raises(medical_client.EgenAPIError, match="조회를 완료하지 못했습니다"):
        provider.list_nearby_ers(lat, lon)
    assert len(calls) == 1

    provider, calls = replay_provider(case, empty_nearby=True)
    assert provider.list_nearby_ers(lat, lon) == []
    assert len(calls) == 1
    assert calls[0]["fixture"] == "empty_items_blank.xml"
