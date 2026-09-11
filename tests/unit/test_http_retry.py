"""http_retry.py 단위 테스트. respx로 실제 네트워크 호출 없이 흉내낸다."""

import httpx
import pytest
import respx

from er_finder.http_retry import is_retryable, request_with_transport_retries


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
def test_request_with_transport_retries_success_without_client():
    route = respx.get("http://test/api").mock(return_value=httpx.Response(200, text="ok"))
    response = request_with_transport_retries(None, "GET", "http://test/api")
    assert response.text == "ok"
    assert route.call_count == 1


@respx.mock
def test_request_with_transport_retries_can_reuse_a_given_client():
    route = respx.get("http://test/api").mock(return_value=httpx.Response(200, text="ok"))
    with httpx.Client() as client:
        response = request_with_transport_retries(client, "GET", "http://test/api")
    assert response.text == "ok"
    assert route.call_count == 1


@respx.mock
def test_request_with_transport_retries_retries_on_500_then_succeeds():
    route = respx.get("http://test/api").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, text="ok")]
    )
    slept = []
    response = request_with_transport_retries(
        None, "GET", "http://test/api", backoff=0, sleep=slept.append
    )
    assert response.text == "ok"
    assert route.call_count == 2
    assert slept == [0]


@respx.mock
def test_request_with_transport_retries_gives_up_after_max_retries():
    route = respx.get("http://test/api").mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        request_with_transport_retries(
            None, "GET", "http://test/api", max_retries=2, backoff=0, sleep=lambda _: None
        )
    assert route.call_count == 3  # 최초 시도 + 재시도 2회


@respx.mock
def test_request_with_transport_retries_404_raises_immediately_without_retry():
    route = respx.get("http://test/api").mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        request_with_transport_retries(
            None, "GET", "http://test/api", max_retries=2, backoff=0, sleep=lambda _: None
        )
    assert route.call_count == 1  # 재시도 없이 바로 실패


def test_connect_error_retries_then_returns_the_successful_response():
    attempts = []
    slept = []

    def handler(request):
        attempts.append(request)
        if len(attempts) < 3:
            raise httpx.ConnectError("temporary connection failure", request=request)
        return httpx.Response(200, text="recovered")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = request_with_transport_retries(
            client, "GET", "https://offline.test/api", backoff=0.25, sleep=slept.append
        )

    assert response.text == "recovered"
    assert len(attempts) == 3
    assert slept == [0.25, 0.25]


def test_persistent_connect_error_stops_at_the_configured_retry_limit():
    attempts = []
    slept = []

    def handler(request):
        attempts.append(request)
        raise httpx.ConnectError("still unavailable", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ConnectError):
            request_with_transport_retries(
                client,
                "GET",
                "https://offline.test/api",
                max_retries=1,
                backoff=0.25,
                sleep=slept.append,
            )

    assert len(attempts) == 2
    assert slept == [0.25]


def test_unsupported_protocol_is_not_retried_as_a_connection_failure():
    attempts = []
    slept = []

    def handler(request):
        attempts.append(request)
        raise httpx.UnsupportedProtocol("unsupported protocol", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.UnsupportedProtocol):
            request_with_transport_retries(
                client, "GET", "https://offline.test/api", sleep=slept.append
            )

    assert len(attempts) == 1
    assert slept == []
