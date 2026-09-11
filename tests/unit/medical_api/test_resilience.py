"""resilience.py 단위 테스트. respx로 실제 네트워크 호출 없이 흉내낸다."""

import httpx
import pytest
import respx

from er_finder.medical_api.resilience import get_with_retry, is_retryable


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://test/api")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


def test_is_retryable_5xx_and_429_are_retryable():
    assert is_retryable(_status_error(500)) is True
    assert is_retryable(_status_error(429)) is True


def test_is_retryable_404_is_not_retryable():
    assert is_retryable(_status_error(404)) is False


def test_is_retryable_timeout_is_retryable():
    request = httpx.Request("GET", "http://test/api")
    assert is_retryable(httpx.TimeoutException("timed out", request=request)) is True


@respx.mock
def test_get_with_retry_success():
    route = respx.get("http://test/api").mock(return_value=httpx.Response(200, text="ok"))
    result = get_with_retry("http://test/api", {})
    assert result == "ok"
    assert route.call_count == 1


@respx.mock
def test_get_with_retry_retries_on_500_then_succeeds():
    route = respx.get("http://test/api").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, text="ok")]
    )
    result = get_with_retry("http://test/api", {}, backoff=0)
    assert result == "ok"
    assert route.call_count == 2


@respx.mock
def test_get_with_retry_gives_up_after_max_retries():
    route = respx.get("http://test/api").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry("http://test/api", {}, max_retries=2, backoff=0)
    assert route.call_count == 3  # 최초 시도 + 재시도 2회


@respx.mock
def test_get_with_retry_404_raises_immediately_without_retry():
    route = respx.get("http://test/api").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        get_with_retry("http://test/api", {}, max_retries=2, backoff=0)
    assert route.call_count == 1  # 재시도 없이 바로 실패
