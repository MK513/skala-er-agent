"""Streamlit entry point for the runner, direct API lookup and isolated UI previews."""

from collections.abc import Callable

import streamlit as st

from er_finder.web.api_view import render_api_view
from er_finder.web.components import page_style, render_header, render_pending, render_reply
from er_finder.web.live import RunnerBackend, load_environment
from er_finder.web.preview import CASES
from er_finder.web.state import WebSession

DEMO_MODE = "화면 검증용 데모"
LIVE_MODE = "실제 API"
TRANSPORT_LABELS = {"car": "자동차", "walk": "도보", "transit": "대중교통"}
KEY_LABELS = {
    "OPENAI_API_KEY": "OpenAI · 대화와 분류",
    "KAKAO_REST_API_KEY": "카카오 · 위치 검색",
    "EGEN_SERVICE_KEY": "E-Gen · 응급의료 정보",
}


def _perform(action: Callable[[], None], notice: str | None = None) -> None:
    st.session_state["ui_notice"] = None
    st.session_state["ui_error"] = None
    try:
        action()
        st.session_state["ui_notice"] = notice
    except Exception:
        st.session_state["ui_error"] = "요청을 처리하지 못했습니다. 연결 상태를 확인해 주세요."


def _ready(web: WebSession) -> bool:
    return not isinstance(web.backend, RunnerBackend) or web.backend.status().connected


def _matches_mode(web: WebSession) -> bool:
    return isinstance(web.backend, RunnerBackend) == (
        st.session_state.get("mode", LIVE_MODE) == LIVE_MODE
    )


def _sync_context(web: WebSession) -> bool:
    """Invalidate decisions before callbacks consume incoming widget values."""
    mode = st.session_state.get("mode", LIVE_MODE)
    scenario = st.session_state.get("scenario", web.scenario)
    transport = st.session_state.get("transport", web.transport)
    mode_changed = st.session_state.get("previous_mode", mode) != mode
    changed = mode_changed or scenario != web.scenario or transport != web.transport
    if mode_changed:
        web.reset()
    web.set_scenario(scenario)
    web.set_transport(transport)
    st.session_state["previous_mode"] = mode
    if changed:
        st.session_state["ui_notice"] = st.session_state["ui_error"] = None
    return bool(changed)


def _perform_current(
    web: WebSession, action: Callable[[], None], *, allow_changed: bool = False
) -> None:
    def current_action() -> None:
        changed = _sync_context(web)
        if not _matches_mode(web):
            return
        if changed and not allow_changed:
            return
        if not _ready(web):
            return
        action()

    _perform(current_action)


def _save_home(web: WebSession) -> None:
    if not _matches_mode(web):
        return
    _perform(
        lambda: web.set_home_address(
            st.session_state["home_address"], consent=st.session_state["home_consent"]
        )
    )


def _clear_home(web: WebSession) -> None:
    if not _matches_mode(web):
        return
    _perform(web.clear_home_address, "기본 주소를 삭제했습니다.")
    st.session_state["home_address"] = ""
    st.session_state["home_consent"] = False


def _forget(web: WebSession) -> None:
    def forget_all() -> None:
        for key in ("live_web", "preview_web"):
            st.session_state[key].forget()
        st.session_state.pop("api_lookup_result", None)
        st.session_state["api_lat"] = 37.497942
        st.session_state["api_lon"] = 127.027621
        st.session_state["api_radius"] = 5

    _perform(forget_all, "두 모드의 대화·저장 정보와 API 조회 기록을 모두 삭제했습니다.")
    st.session_state["home_address"] = ""
    st.session_state["home_consent"] = False


def _connect(web: WebSession) -> None:
    def connect() -> None:
        if st.session_state.get("mode", LIVE_MODE) != LIVE_MODE:
            return
        _sync_context(web)
        web.reset()
        web.backend.connect(transport=web.transport)

    _perform(connect)


def _current_session() -> WebSession:
    load_environment()
    if "live_web" not in st.session_state:
        st.session_state["live_web"] = WebSession(backend=RunnerBackend())
    if "preview_web" not in st.session_state:
        st.session_state["preview_web"] = WebSession()
    live = st.session_state.get("mode", LIVE_MODE) == LIVE_MODE
    web = st.session_state["live_web" if live else "preview_web"]
    previous = st.session_state.get("web")
    if previous is not None and previous is not web:
        previous.reset()
        web.reset()
        st.session_state["home_address"] = ""
        st.session_state["home_consent"] = False
        st.session_state["ui_notice"] = st.session_state["ui_error"] = None
    st.session_state["web"] = web
    return web


def _sidebar(web: WebSession) -> bool:
    with st.sidebar:
        st.markdown("## ✚ ER Finder")
        st.caption("응급실 탐색 · 방문 계획")
        st.divider()
        mode = st.radio("실행 모드", [LIVE_MODE, DEMO_MODE], key="mode")
        live = mode == LIVE_MODE
        st.selectbox(
            "이동수단",
            list(TRANSPORT_LABELS),
            format_func=lambda value: TRANSPORT_LABELS[value],
            key="transport",
        )
        with st.expander("화면 검토용 예시", expanded=not live):
            st.selectbox(
                "화면 시나리오",
                list(CASES),
                format_func=lambda value: CASES[value],
                key="scenario",
                disabled=live,
            )
            st.caption("고정 합성 예시이며, 실제 검색 결과가 아닙니다.")
            st.button(
                "선택한 화면 확인",
                key="run_scenario",
                type="primary",
                width="stretch",
                disabled=live,
                on_click=_perform_current,
                args=(web, lambda: web.submit(f"{CASES[web.scenario]} 화면 확인")),
                kwargs={"allow_changed": True},
            )
        _sync_context(web)
        if live:
            status = web.backend.status()
            st.caption("● 연결됨" if status.connected else "○ 에이전트 연결 확인 필요")
            st.button(
                "다시 연결 확인" if status.connected else "에이전트 연결 확인",
                key="connect_runner",
                width="stretch",
                type="primary",
                on_click=_connect,
                args=(web,),
            )
        st.divider()
        left, right = st.columns(2)
        left.button(
            "새 대화",
            key="new_conversation",
            width="stretch",
            on_click=_perform,
            args=(web.reset, "대화와 승인 대기를 초기화했습니다. 저장 정보는 유지됩니다."),
        )
        right.button(
            "기록 전체 삭제",
            key="forget_all",
            width="stretch",
            on_click=_forget,
            args=(web,),
        )
        pending = bool(web.result and web.result.pending_approval)
        st.button(
            "다시 조회" if live else "마지막 화면 새로고침",
            key="refresh_search",
            width="stretch",
            disabled=not _ready(web) or web.result is None or pending,
            on_click=_perform_current,
            args=(web, web.refresh),
        )
        with st.expander("기본 주소", expanded=False):
            home = web.backend.profile.get_home_address()
            if home:
                st.caption("저장된 주소")
                st.text(home)
            with st.form("home_form"):
                st.text_input("기본 주소 입력", key="home_address", max_chars=150)
                st.checkbox("이 브라우저 세션에 기본 주소 저장에 동의합니다.", key="home_consent")
                st.form_submit_button(
                    "주소 저장",
                    key="save_home",
                    on_click=_save_home,
                    args=(web,),
                    width="stretch",
                )
            st.button(
                "기본 주소 삭제",
                key="clear_home",
                on_click=_clear_home,
                args=(web,),
                disabled=home is None,
                width="stretch",
            )
        with st.expander("저장한 방문 계획", expanded=False):
            visits = web.backend.profile.get_recent_visits()
            if not visits:
                st.caption("아직 저장한 방문 계획이 없습니다.")
            for visit in visits:
                st.text(visit["name"])
                st.caption(visit["saved_at"])
            st.caption("방문 계획 저장은 병원 예약이나 접수가 아닙니다.")
            if not live:
                st.caption("화면 검토용 모드에서 저장한 합성 방문 계획입니다.")
        st.caption(
            "실제 모드와 검토용 모드의 기록은 분리됩니다. 저장 정보는 서버 메모리에 보관됩니다."
        )
    return live


def _connection_view() -> None:
    backend = st.session_state["live_web"].backend
    status = backend.status()
    st.subheader("서비스 연결 상태")
    st.caption("키의 설정 여부를 표시합니다. 인증 성공 여부는 실제 요청 이후에 확인할 수 있습니다.")
    for column, (key, label) in zip(st.columns(3), KEY_LABELS.items(), strict=True):
        with column:
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.write("설정됨" if status.checks.get(key) else "설정 필요")
    if status.connected:
        st.success(status.message)
    else:
        st.info(status.message)
    with st.expander("로컬 실행 설정", expanded=False):
        st.markdown(
            "프로젝트의 `.env`에 다음 키를 설정한 뒤 **에이전트 연결 확인**을 눌러주세요. "
            "이미 실행 환경에 설정한 값은 그대로 사용합니다."
        )
        st.code(
            "OPENAI_API_KEY=...\nKAKAO_REST_API_KEY=...\nEGEN_SERVICE_KEY=...", language="dotenv"
        )
        st.caption("키 값은 화면에 표시하지 않습니다. .env 파일은 Git에 올리지 않습니다.")
    st.markdown("**현재 연결 범위**")
    st.markdown(
        "- 응급실 찾기: 에이전트 연결 후 대화·후보 선택·승인 요청을 전달합니다.\n"
        "- 의료 API 조회: 좌표를 입력해 E-Gen의 주변 기관 목록을 직접 조회합니다.\n"
        "- 화면 검토용 예시: 실제 API 호출 없이 카드·승인·삭제 흐름을 확인합니다."
    )
    st.caption(
        "현재 병합 코드의 연결 오류는 별도 수정 대상입니다. "
        "연결 실패 시 합성 결과로 대체하지 않습니다."
    )


def _search_view(web: WebSession, *, live: bool) -> None:
    if live:
        status = web.backend.status()
        if status.connected:
            st.success("에이전트가 연결되었습니다. 위치와 증상을 입력해 주세요.")
        else:
            st.info(status.message)
            st.caption("현재는 ‘의료 API 조회’에서 주변 기관 목록을 별도로 확인할 수 있습니다.")
    else:
        st.warning(
            "화면 검증용 데모 · 가상 병원과 고정 시나리오입니다. "
            "실제 응급실 안내에 사용하지 마세요."
        )
        st.caption(f"현재 시나리오 · {CASES[web.scenario]} | 실제 API·모델 호출 없음")
    if st.session_state.get("ui_error"):
        st.error(st.session_state["ui_error"])
    elif st.session_state.get("ui_notice"):
        st.success(st.session_state["ui_notice"])
    if web.messages:
        with st.expander("대화 기록", expanded=True):
            for message in web.messages:
                with st.chat_message(message.role):
                    st.text(message.text)
    result = web.result
    if result:
        if result.note:
            (st.error if not live and web.scenario == "error" else st.info)(result.note)
        if result.reply:
            render_reply(
                result.reply,
                lambda hpid: _perform_current(web, lambda: web.select_hospital(hpid)),
                selection_disabled=result.pending_approval is not None or not _ready(web),
                source_label="실제 에이전트 응답" if live else "화면 검증용 데모",
            )
        if result.pending_approval:
            render_pending(
                result.pending_approval,
                lambda approved: _perform_current(web, lambda: web.decide(approved)),
            )
    else:
        with st.container(border=True):
            st.subheader("위치와 상황을 알려주세요" if live else "어떤 화면을 확인할까요?")
            st.write(
                "현재 계신 동네나 주소, 불편한 증상을 함께 입력하면 응급실 탐색을 시작합니다."
                if live
                else "왼쪽에서 시나리오를 선택하고 ‘선택한 화면 확인’을 눌러보세요."
            )
            for column, title, detail in zip(
                st.columns(3),
                ("01  위치와 증상", "02  응급실 후보", "03  방문 계획"),
                ("현재 상황 입력", "거리·병상·수용 정보 확인", "직접 선택하고 저장 승인"),
                strict=True,
            ):
                column.markdown(f"**{title}**")
                column.caption(detail)
    pending = bool(web.result and web.result.pending_approval)
    text = st.chat_input(
        "예: 강남구 역삼동, 손가락이 부었어요" if live else "화면 확인 메시지를 입력하세요",
        key="message",
        max_chars=2000,
        disabled=not _ready(web) or pending,
    )
    if text:
        with st.spinner("응급실 정보를 확인하고 있습니다…"):
            _perform_current(web, lambda: web.submit(text), allow_changed=True)
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="ER Finder · 응급실 안내", page_icon="✚", layout="wide")
    page_style()
    web = _current_session()
    live = _sidebar(web)
    render_header()
    search, api, connection = st.tabs(["응급실 찾기", "의료 API 조회", "연결 상태"])
    with search:
        _search_view(web, live=live)
    with api:
        render_api_view()
    with connection:
        _connection_view()
    st.divider()
    st.caption(
        "생명이 위급한 상황에서는 즉시 119에 연락하세요. 응급실 방문 전 전화 확인을 권장합니다."
    )


if __name__ == "__main__":
    main()
