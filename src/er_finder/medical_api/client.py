"""E-Gen API 호출 + 병상 캐시를 합쳐서 실제 도구 함수를 만드는 모듈.

interfaces.md 2. 도구 인터페이스, api-contract.md 1.3~1.6을 따른다.
모든 함수는 예외를 밖으로 던지지 않는다 - 실패하면 빈 목록/빈 dict로 돌려준다.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from urllib.parse import unquote

import httpx
from dotenv import load_dotenv

from er_finder.http_retry import request_with_transport_retries

from . import cache, parser

load_dotenv()

BASE_URL = os.environ.get("EGEN_BASE_URL", "http://apis.data.go.kr/B552657/ErmctInfoInqireService")
# 공공데이터포털 서비스키가 이미 percent-encoded인 경우가 있어 미리 한 번 풀어둔다.
SERVICE_KEY = unquote(os.environ.get("EGEN_SERVICE_KEY", ""))
TIMEOUT = float(os.environ.get("ER_REQUEST_TIMEOUT", "5"))
MAX_RETRIES = int(os.environ.get("ER_MAX_RETRIES", "2"))
BACKOFF = float(os.environ.get("ER_RETRY_BACKOFF", "1"))
BED_CACHE_TTL = float(os.environ.get("ER_BED_CACHE_TTL", "60"))
STALE_MINUTES = float(os.environ.get("ER_STALE_MINUTES", "15"))

# TriageAssessment.condition -> mkioskty 번호 (api-contract.md §1.5)
# "중증외상"은 대응하는 코드가 없어 Sprint 2(외상센터 API)로 미룬다.
CONDITION_TO_MKIOSKTY = {
    "심근경색": [1],
    "뇌출혈": [3, 4],
    "뇌졸중": [2],
    "화상": [19],
    "분만": [16],
}


def _build_params(extra: dict, num_of_rows: int = 100) -> dict:
    return {"serviceKey": SERVICE_KEY, "pageNo": 1, "numOfRows": num_of_rows, **extra}


def _call(endpoint: str, params: dict) -> str | None:
    """E-Gen을 호출해 응답 텍스트를 돌려준다. 실패하면 None을 돌려준다."""
    url = BASE_URL.rstrip("/") + endpoint
    try:
        response = request_with_transport_retries(
            None,
            "GET",
            url,
            params=params,
            timeout=TIMEOUT,
            max_retries=MAX_RETRIES,
            backoff=BACKOFF,
        )
    except httpx.HTTPError:
        return None
    return response.text


def _is_stale(beds_updated_at: str | None) -> bool:
    """hvidate가 ER_STALE_MINUTES(기본 15분)보다 오래됐으면 True."""
    if beds_updated_at is None:
        return True
    updated_at = datetime.fromisoformat(beds_updated_at)
    return datetime.now() - updated_at > timedelta(minutes=STALE_MINUTES)


def list_nearby_ers(lat: float, lon: float, radius_km: int = 5) -> list[dict]:
    """좌표 반경 내 응급의료기관 목록. 거리 오름차순으로 돌려준다."""
    params = _build_params({"WGS84_LAT": lat, "WGS84_LON": lon})
    xml_text = _call("/getEgytLcinfoInqire", params)
    if xml_text is None:
        return []

    try:
        rows = parser.parse_nearby(xml_text)
    except parser.EgenResponseError:
        return []

    nearby = [
        row for row in rows if row["distance_km"] is not None and row["distance_km"] <= radius_km
    ]
    nearby.sort(key=lambda row: row["distance_km"])
    return nearby


def get_er_bed_status(
    sido: str, sigungu: str, hpids: list[str], bed_cache: dict | None = None
) -> list[dict]:
    """실시간 가용병상 조회.

    hpids로 필터링해서 돌려준다. 60초 캐시를 쓰고, 실패하면 캐시(있으면)로 폴백한다.
    bed_cache는 대화 세션 동안 유지되는 dict를 넘겨받아야 한다 (interfaces.md §3 bed_cache).
    """
    if bed_cache is None:
        bed_cache = {}
    key = cache.make_key(sido, sigungu)

    rows = cache.get(bed_cache, key, ttl=BED_CACHE_TTL)
    forced_stale = False

    if rows is None:
        params = _build_params({"STAGE1": sido, "STAGE2": sigungu})
        xml_text = _call("/getEmrrmRltmUsefulSckbdInfoInqire", params)
        rows = None
        if xml_text is not None:
            try:
                rows = parser.parse_bed_status(xml_text)
                cache.save(bed_cache, key, rows)
            except parser.EgenResponseError:
                rows = None

        if rows is None:
            # 재시도까지 실패 -> 만료됐어도 캐시에 남아있는 값으로 폴백
            expired = bed_cache.get(key)
            if expired is None:
                return []
            rows = expired[0]
            forced_stale = True

    result = []
    for row in rows:
        if row["hpid"] not in hpids:
            continue
        stale = forced_stale or _is_stale(row["beds_updated_at"])
        result.append({**row, "stale": stale})
    return result


def _combine_mkioskty(mkioskty: dict, codes: list[int]) -> bool | None:
    """codes 중 하나라도 True면 True, 전부 False면 False, 그 외엔 None (확인 불가)."""
    values = [mkioskty.get(code) for code in codes]
    if any(value is True for value in values):
        return True
    if all(value is False for value in values):
        return False
    return None


def get_severe_acceptance(sido: str, sigungu: str, condition: str) -> list[dict]:
    """중증질환자 수용가능정보 조회. condition에 대응하는 mkioskty 번호를 확인한다."""
    codes = CONDITION_TO_MKIOSKTY.get(condition)
    if not codes:
        # 대응 코드가 없는 조건(예: 중증외상)은 조회하지 않는다.
        return []

    params = _build_params({"STAGE1": sido, "STAGE2": sigungu})
    xml_text = _call("/getSrsillDissAceptncPosblInfoInqire", params)
    if xml_text is None:
        return []

    try:
        rows = parser.parse_severe(xml_text)
    except parser.EgenResponseError:
        return []

    return [
        {
            "hpid": row["hpid"],
            "name": row["name"],
            "acceptable": _combine_mkioskty(row["mkioskty"], codes),
        }
        for row in rows
    ]


def get_er_detail(hpid: str) -> dict:
    """기관 기본정보 조회. 실패하면 빈 dict."""
    params = _build_params({"HPID": hpid})
    xml_text = _call("/getEgytBassInfoInqire", params)
    if xml_text is None:
        return {}

    try:
        return parser.parse_er_detail(xml_text)
    except parser.EgenResponseError:
        return {}
