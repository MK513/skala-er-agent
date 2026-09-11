"""Exercise actual nearby parsing through Streamlit; no external requests are allowed."""

from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

APP = "from er_finder.web.api_view import render_api_view\nrender_api_view()"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "egen"


def open_view():
    app = AppTest.from_string(APP, default_timeout=10).run()
    assert not app.exception
    return app


def visible_text(app):
    return "\n".join(
        str(element.value)
        for kind in ("text", "markdown", "caption", "info", "warning", "error", "success")
        for element in getattr(app, kind)
    )


@pytest.fixture
def nearby_transport(monkeypatch):
    monkeypatch.setenv("EGEN_SERVICE_KEY", "offline-synthetic-key")
    from er_finder.medical_api import client, resilience

    monkeypatch.setattr(client, "SERVICE_KEY", "offline-synthetic-key")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, text=(FIXTURES / "nearby_gangnam.xml").read_text())

    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        monkeypatch.setattr(resilience.httpx, "get", transport.get)
        yield requests


def test_missing_key_disables_api_form_without_importing_the_client(monkeypatch):
    import builtins

    monkeypatch.setenv("EGEN_SERVICE_KEY", "")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("er_finder.medical_api"):
            raise AssertionError("medical_api must load only after explicit query")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    app = open_view()
    assert app.button(key="api_search").disabled
    assert all(widget.disabled for widget in app.number_input)
    assert "EGEN_SERVICE_KEY" in visible_text(app)
    assert not app.dataframe


def test_query_displays_recorded_source_data_and_reruns_make_no_request(nearby_transport):
    app = open_view()
    app.run()
    assert nearby_transport == []
    app.button(key="api_search").click().run()
    assert not app.exception
    assert len(nearby_transport) == 1
    query = nearby_transport[0].url.params
    assert float(query["WGS84_LAT"]) == 37.497942
    assert float(query["WGS84_LON"]) == 127.027621
    table = app.dataframe[0].value
    assert "A1100141" in list(table["기관 ID"])
    assert table.loc[table["기관 ID"] == "A1100141", "기관명"].item() == "강남베드로병원"
    assert all(value == "확인 불가" for value in table["주소"])
    assert any(value != "확인 불가" for value in table["대표전화"])
    assert "원자료" in visible_text(app)
    assert "offline-synthetic-key" not in visible_text(app)
    app.number_input(key="api_lat").set_value(37.6).run()
    assert len(nearby_transport) == 1
    assert app.dataframe[0].value.equals(table)
    assert "37.497942" in visible_text(app)


def test_submit_uses_new_coordinates_and_radius_in_the_same_event(nearby_transport):
    app = open_view()
    app.number_input(key="api_lat").set_value(37.5)
    app.number_input(key="api_lon").set_value(127.1)
    app.selectbox(key="api_radius").set_value(10)
    app.button(key="api_search").click().run()
    assert not app.exception
    assert len(nearby_transport) == 1
    query = nearby_transport[0].url.params
    assert float(query["WGS84_LAT"]) == 37.5
    assert float(query["WGS84_LON"]) == 127.1
    assert "10 km" in visible_text(app)
    assert any(value > 5 for value in app.dataframe[0].value["거리 (km)"])


def test_empty_or_failed_source_does_not_claim_no_hospitals(monkeypatch):
    monkeypatch.setenv("EGEN_SERVICE_KEY", "offline-synthetic-key")
    from er_finder.medical_api import resilience

    empty_xml = (FIXTURES / "empty_items_blank.xml").read_text()
    response_transport = httpx.MockTransport(lambda request: httpx.Response(200, text=empty_xml))
    with httpx.Client(transport=response_transport) as transport:
        monkeypatch.setattr(resilience.httpx, "get", transport.get)
        app = open_view()
        app.button(key="api_search").click().run()
    assert not app.exception
    assert not app.dataframe
    assert "빈 응답" in visible_text(app)
    assert "조회 실패" in visible_text(app)


def test_failure_clears_old_rows_and_hides_raw_exception(nearby_transport, monkeypatch):
    from er_finder.medical_api import client

    app = open_view()
    app.button(key="api_search").click().run()
    assert app.dataframe

    def unavailable(*args, **kwargs):
        raise RuntimeError("PRIVATE_REQUEST serviceKey=secret-dummy-key")

    monkeypatch.setattr(client, "list_nearby_ers", unavailable)
    app.button(key="api_search").click().run()
    assert not app.exception
    assert app.error
    assert not app.dataframe
    assert "PRIVATE_REQUEST" not in visible_text(app)
    assert "secret-dummy-key" not in visible_text(app)
    app.run()
    assert app.error
    assert not app.dataframe


def test_other_browser_session_does_not_receive_previous_query(nearby_transport):
    first = open_view()
    first.button(key="api_search").click().run()
    assert first.dataframe
    second = open_view()
    assert not second.dataframe
    assert len(nearby_transport) == 1
