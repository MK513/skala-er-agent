"""검증된 화면 응답의 표시만 담당한다. 조회·분류·저장 규칙은 구현하지 않는다."""

from collections.abc import Callable
from html import escape

import streamlit as st

from er_finder.memory.visit_plan import PendingVisitPlan
from er_finder.web.contracts import UIHospital, UIReply


def page_style() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f8fafb; }
        .block-container { max-width: 1200px; padding-top: 3.5rem; padding-bottom: 2rem; }
        [data-testid="stSidebar"] { background: #eff4f5; border-right: 1px solid #dce8e9; }
        [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px; }
        h1, h2, h3 { color: #163b42; letter-spacing: -0.035em; }
        h1 { font-size: 2.55rem !important; }
        [data-baseweb="tab-list"] { gap: 1.5rem; margin: .8rem 0 1.4rem; }
        [data-baseweb="tab"] { font-size: 1rem; }
        [data-testid="stMetricValue"] { color: #126b72; }
        .eyebrow { color: #387c81; font-weight: 700; letter-spacing: .15em;
                   font-size: .72rem; margin-bottom: .5rem; }
        .hospital-name { color: #173e44; font-size: 1.16rem; font-weight: 750;
                         margin: .35rem 0 .8rem; }
        .hospital-rank { color: #34777c; font-weight: 700; font-size: .8rem; }
        .intro { color: #52646b; font-size: 1.04rem; line-height: 1.7; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown('<div class="eyebrow">ER FINDER · 응급실 탐색</div>', unsafe_allow_html=True)
    st.title("응급실 안내, 한눈에")
    st.markdown(
        '<p class="intro">가까운 후보를 살펴보고, 방문 계획을 직접 확인하세요.</p>',
        unsafe_allow_html=True,
    )


def render_hospital(
    hospital: UIHospital,
    rank: int,
    on_select: Callable[[str], None],
    *,
    disabled: bool,
) -> None:
    with st.container(border=True):
        st.markdown(
            f'<div class="hospital-rank">후보 {rank:02d}</div>'
            f'<div class="hospital-name">{escape(hospital.name)}</div>',
            unsafe_allow_html=True,
        )
        distance, beds = st.columns(2)
        distance.metric("거리", f"{hospital.distance_km:.1f} km")
        beds.metric(
            "가용 병상",
            "확인 불가"
            if hospital.er_beds_available is None
            else f"{hospital.er_beds_available}개",
        )
        st.caption("주소")
        st.text(hospital.address or "확인 불가")
        st.caption("병원 대표전화")
        st.text(hospital.er_tel or "확인 불가")
        acceptance = {"yes": "수용 가능", "no": "수용 불가", "unknown": "확인 불가"}
        st.caption(f"중증 수용 여부 · {acceptance[hospital.accepts_condition]}")
        if hospital.is_stale:
            st.warning("갱신 지연 · 방문 전 전화 확인이 필요합니다.")
        if hospital.is_cached:
            st.caption("캐시 정보 · 이전 조회 결과")
        st.caption(f"갱신 시각 · {hospital.beds_updated_at or '확인 불가'}")
        st.button(
            "이 병원 선택",
            key=f"select_{hospital.hpid}",
            on_click=on_select,
            args=(hospital.hpid,),
            disabled=disabled,
            width="stretch",
        )


def render_reply(
    reply: UIReply,
    on_select: Callable[[str], None],
    *,
    selection_disabled: bool = False,
    source_label: str = "실제 에이전트 응답",
) -> None:
    if reply.call_119_first:
        st.error("119에 즉시 신고하세요. 검색 결과를 기다리지 마세요.", icon="🚨")
    st.subheader("응급실 후보")
    st.caption(
        f"{source_label} · 검색 반경 {reply.search_radius_km} km · 후보 {len(reply.hospitals)}곳"
    )
    if not reply.hospitals:
        st.info(reply.no_candidate_reason or "표시할 후보가 없습니다.")
    else:
        columns = st.columns(len(reply.hospitals), gap="medium")
        for rank, (column, hospital) in enumerate(zip(columns, reply.hospitals, strict=True), 1):
            with column:
                render_hospital(hospital, rank, on_select, disabled=selection_disabled)
    st.info(reply.next_action, icon="ℹ️")
    st.caption(f"응답 시각 · {reply.data_timestamp}")
    st.caption(reply.disclaimer)


def render_pending(
    plan: PendingVisitPlan,
    on_decision: Callable[[bool], None],
) -> None:
    with st.container(border=True):
        st.subheader("방문 계획을 저장할까요?")
        st.caption("아래 내용을 확인한 후 승인하세요. 병원 예약이나 접수는 진행되지 않습니다.")
        st.text(f"병원: {plan.name}")
        st.text(f"증상 요약: {plan.symptom_summary}")
        st.caption("이 브라우저 세션의 메모리에 저장됩니다.")
        approve, reject = st.columns(2)
        approve.button(
            "승인하고 저장",
            key="approve_visit",
            type="primary",
            width="stretch",
            on_click=on_decision,
            args=(True,),
        )
        reject.button(
            "저장하지 않기",
            key="reject_visit",
            width="stretch",
            on_click=on_decision,
            args=(False,),
        )
