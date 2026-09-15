import ast
import re

RETRYABLE_STATUSES = {408, 409, 425, 429}

_EXCEPTION_BLOCK = re.compile(r"<exception>\s*(.*?)\s*</exception>", re.DOTALL)
_ERROR_CODE_BODY = re.compile(r"Error code:\s*(\d{3})\s*-\s*(\{.*\})\s*$", re.DOTALL)
_REQUEST_ID = re.compile(r"\s*\(request id:[^)]*\)")


def _status(exc: BaseException):
    code = getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
    return code


def is_retryable(exc: BaseException) -> bool:
    code = _status(exc)
    if isinstance(code, int):
        return code in RETRYABLE_STATUSES or code >= 500
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__
    return "Timeout" in name or "Connection" in name


def _unwrap(text: str):
    """Reduce instructor's <failed_attempts> wrapper and OpenAI-style
    'Error code: NNN - {...}' bodies to (status, human message)."""
    m = _EXCEPTION_BLOCK.search(text)
    if m:
        text = m.group(1)
    m = _ERROR_CODE_BODY.search(text)
    if not m:
        return None, text
    status = int(m.group(1))
    try:
        body = ast.literal_eval(m.group(2))
    except (ValueError, SyntaxError):
        return status, m.group(2)
    err = body.get("error", body) if isinstance(body, dict) else body
    message = err.get("message") if isinstance(err, dict) else None
    return status, _REQUEST_ID.sub("", str(message or err))


def error_message(exc: BaseException, limit: int = 300) -> str:
    code = _status(exc)
    text = str(exc) or type(exc).__name__
    inner_code, text = _unwrap(text)
    if not isinstance(code, int):
        code = inner_code
    msg = f"HTTP {code}: {text}" if isinstance(code, int) else text
    return msg[:limit]
