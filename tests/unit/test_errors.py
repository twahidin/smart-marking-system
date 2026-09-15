import httpx
import openai

from sms.providers.errors import error_message, is_retryable


def _status_error(code):
    resp = httpx.Response(code, request=httpx.Request("POST", "https://x"))
    return openai.APIStatusError("boom", response=resp, body=None)


def test_429_and_5xx_retryable():
    assert is_retryable(_status_error(429))
    assert is_retryable(_status_error(503))


def test_4xx_not_retryable():
    assert not is_retryable(_status_error(400))
    assert not is_retryable(_status_error(401))
    assert not is_retryable(ValueError("bad"))


def test_connection_and_timeout_retryable():
    req = httpx.Request("POST", "https://x")
    assert is_retryable(openai.APIConnectionError(request=req))
    assert is_retryable(openai.APITimeoutError(request=req))
    assert is_retryable(TimeoutError())


def test_error_message_trims():
    assert len(error_message(RuntimeError("x" * 500))) <= 300
    assert error_message(_status_error(429)).startswith("HTTP 429")


def test_error_message_unwraps_instructor_failed_attempts():
    wrapped = RuntimeError(
        "<failed_attempts>\n<generation number=\"1\">\n<exception>\nError code: 503 - {'error': "
        "{'code': 'model_not_found', 'message': 'No available channel for model z-ai/glm-5.3-free "
        "under group default (distributor) (request id: 2026abc)', 'type': 'api_error'}}\n"
        "</exception>\n<completion>...</completion>\n</generation>\n</failed_attempts>"
    )
    msg = error_message(wrapped)
    assert msg.startswith("HTTP 503: No available channel for model z-ai/glm-5.3-free")
    assert "<" not in msg and "request id" not in msg


def test_error_message_unwraps_plain_error_code_body():
    exc = RuntimeError("Error code: 401 - {'error': {'message': 'Invalid API key', 'type': 'auth'}}")
    assert error_message(exc) == "HTTP 401: Invalid API key"
