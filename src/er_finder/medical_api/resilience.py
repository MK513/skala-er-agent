"""외부 API 호출 시 타임아웃·재시도를 처리하는 모듈

- 타임아웃: 기본 5초
- 재시도 대상: 타임아웃, 5xx, 429 (최대 2회, 매번 1초 대기)
- 재시도 제외: 그 외 4xx 등 - 재시도해도 똑같이 실패할 오류라 바로 예외
"""

from __future__ import annotations

import time

import httpx


def is_retryable(error: httpx.HTTPError) -> bool:
    """타임아웃, 5xx, 429만 재시도 대상으로 본다."""
    if isinstance(error, httpx.TimeoutException):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        return status_code == 429 or status_code >= 500
    return False


def get_with_retry(
    url: str,
    params: dict,
    *,
    timeout: float = 5,
    max_retries: int = 2,
    backoff: float = 1,
) -> str:
    """GET 요청을 보내고 응답 텍스트(원문)를 돌려준다.

    타임아웃·5xx·429가 나면 최대 max_retries번 다시 시도한다(시도 사이에 backoff초 대기)
    그 외 오류는 재시도하지 않고 바로 예외 던짐
    재시도를 다 쓰고도 실패하면 마지막 오류를 그대로 던짐
    """
    last_error: httpx.HTTPError | None = None

    for attempt in range(max_retries + 1):
        try:
            response = httpx.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as error:
            last_error = error
            if not is_retryable(error):
                raise
            if attempt < max_retries:
                time.sleep(backoff)

    raise last_error  # type: ignore[misc]
