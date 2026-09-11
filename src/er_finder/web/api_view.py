"""Explicit E-Gen location lookup, separate from agent recommendations."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from er_finder.web.live import credential_status


def render_api_view() -> None:
    """Query the existing medical client only on submit; retain the last result per session."""
    st.subheader("주변 응급의료기관 · API 조회")
    st.caption("E-Gen 위치정보 원자료 · 좌표와 반경을 입력한 후 조회하세요.")
    st.info("기관 위치와 대표전화를 조회합니다. 가용 병상과 진료 가능 여부는 전화로 확인하세요.")
    configured = credential_status()["EGEN_SERVICE_KEY"]
    if not configured:
        st.warning("EGEN_SERVICE_KEY 설정이 필요합니다. 서버의 환경변수 또는 .env를 확인하세요.")

    with st.form("api_location_form"):
        latitude_column, longitude_column, radius_column = st.columns((2, 2, 1))
        lat = latitude_column.number_input(
            "위도",
            min_value=-90.0,
            max_value=90.0,
            value=37.497942,
            format="%.6f",
            key="api_lat",
            disabled=not configured,
        )
        lon = longitude_column.number_input(
            "경도",
            min_value=-180.0,
            max_value=180.0,
            value=127.027621,
            format="%.6f",
            key="api_lon",
            disabled=not configured,
        )
        radius = radius_column.selectbox(
            "반경",
            (5, 10, 20, 30),
            format_func=lambda value: f"{value} km",
            key="api_radius",
            disabled=not configured,
        )
        submitted = st.form_submit_button(
            "주변 기관 조회",
            key="api_search",
            type="primary",
            width="stretch",
            disabled=not configured,
        )

    if submitted and configured:
        result = {
            "lat": lat,
            "lon": lon,
            "radius": radius,
            "queried_at": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST"),
            "rows": [],
            "error": False,
        }
        try:
            with st.spinner("E-Gen 기관 정보를 조회하고 있습니다…"):
                from er_finder.medical_api.client import list_nearby_ers

                rows = list_nearby_ers(lat, lon, radius)
                result["rows"] = [
                    {
                        "기관 ID": row.get("hpid") or "확인 불가",
                        "기관명": row.get("name") or "확인 불가",
                        "거리 (km)": row.get("distance_km"),
                        "주소": row.get("address") or "확인 불가",
                        "대표전화": row.get("er_tel") or "확인 불가",
                    }
                    for row in rows
                ]
        except Exception:
            # Import/configuration errors can include credentials and request URLs.
            result["error"] = True
        st.session_state["api_lookup_result"] = result

    result = st.session_state.get("api_lookup_result")
    if result is None:
        st.caption("조회 버튼을 누르면 입력한 좌표 주변의 기관 목록이 표시됩니다.")
        return

    st.caption(
        f"마지막 조회 · 위도 {result['lat']:.6f}, 경도 {result['lon']:.6f} · "
        f"반경 {result['radius']} km · {result['queried_at']}"
    )
    if result["error"]:
        st.error("기관 정보를 조회하지 못했습니다. 설정과 연결 상태를 확인한 후 다시 조회하세요.")
    elif not result["rows"]:
        st.info(
            "표시할 기관 정보가 없습니다. 빈 응답이거나 조회 실패일 수 있습니다. "
            "반경과 설정을 확인한 후 다시 조회하세요."
        )
    else:
        st.caption(f"조회 결과 · {len(result['rows'])}곳 · 거리순")
        st.dataframe(
            result["rows"],
            hide_index=True,
            width="stretch",
            column_config={"거리 (km)": st.column_config.NumberColumn(format="%.2f")},
        )
        st.caption("주소 등 응답에 없는 항목은 ‘확인 불가’로 표시합니다.")
